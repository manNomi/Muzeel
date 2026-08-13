import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

import pymysql.cursors

from EliminationUtils import EliminationUtils
from ModernFunctionParser import ModernFunctionParser
"""Data store for the JS files, both the original and updated"""


class DataStore:
    def __init__(self, url: str, db_details: map) -> None:
        """Initializes data store"""
        self.url = url # Url of the page being processed
        self.data_map = {} # Map of form {request_url: {"original": original_code, "updated": updated_code}}
        self.function_id_map = {} # Map of form {request_url: set(function_identifiers)}. For each request_url, we keep the set of function identifiers in the file, 
        self.function_metadata_map = {}
        self.instrumentation_errors = {}
        self.excluded_request_urls = {}
        self.request_url_content_file_map = {} # Map of form {request_url: file_path_of_original_code }. Makes retrieval easier
        self.cache_directory = db_details.get("cache_directory", "")+"/data/" # Directory of folder where data is cached.
        self.db = db_details.get("database", "db")
        self.protected_content_markers = tuple(
            db_details.get("protected_content_markers", ("Sentry", "sentry"))
        )
        self.connection = pymysql.connect(
            host=db_details.get("host", "localhost"),
            user=db_details.get("user", "root"),
            password=db_details.get("password", ""),
            port=db_details.get("port", 3306),
            database=self.db,
        )

        self.__populate_data_map()
        self.__populate_function_id_map()


    def __get_file_content(self, content_file_path: str) -> str:
        """Retrieves file content from file path

        Parameters:
        content_file_path (int): Path to file containing the original source code

        Returns:
        str: File content
        """

        with open(self.cache_directory + "/" + content_file_path, "r", errors="ignore") as file:
            return file.read()

    def __populate_data_map(self) -> None:
        """Populates the data map. For each Javascript file requested by the page, we keep a map of the request_url to the content of the original file 
        as well as the updated file content (the file content Muzeel updates as it carries out dce).

        This is stored in the form {request_url: {"original": original_file_content, "updated": updated_file_content }}

        This function also populates the request_url_content_file_map
        """

        print("Getting JS files for", self.url)

        with self.connection.cursor() as cursor:
            sql = "SELECT requestUrl, contFilePath FROM {0}.cachedPages WHERE (initiatingUrl='{1}' OR initiatingUrl='{1}/') AND updateFilePath IS NOT NULL".format(
                self.db, self.url)
            cursor.execute(sql)
            result = cursor.fetchall()
            for js_file in result:
                [request_url, content_file_path] = js_file
                file_content = self.__get_file_content(content_file_path)
                print(content_file_path)
                self.data_map[request_url] = {"original": file_content, "updated": file_content}
                self.request_url_content_file_map[request_url] = content_file_path

    def __populate_function_id_map(self) -> None:
        """Populates the function_id_map. We maintain a function_id set for each javascript file requested by the page.
        Function ids are composed of "request_url | function_start_byte_offset | function_end_byte_offset".
        After the function_id_map is populated, log statements are added to the updated content file in the data_map by calling __add_log_statements_to_update_file. 
        """

        print("Retrieving functions in JS files with the modern parser")
        parser = ModernFunctionParser()
        site_origin = urlsplit(self.url)
        for request_url in self.data_map:
            script_content = self.data_map[request_url]["original"]
            self.function_id_map[request_url] = set()
            self.function_metadata_map[request_url] = {}
            request_origin = urlsplit(request_url)
            if (
                request_origin.scheme,
                request_origin.netloc,
            ) != (site_origin.scheme, site_origin.netloc):
                self.excluded_request_urls[request_url] = "cross_origin_preserved"
                continue
            protected_marker = next(
                (
                    marker
                    for marker in self.protected_content_markers
                    if marker in script_content
                ),
                None,
            )
            if protected_marker is not None:
                self.excluded_request_urls[request_url] = (
                    f"protected_runtime_marker:{protected_marker.lower()}"
                )
                continue
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".js", encoding="utf-8", delete=False
                ) as source:
                    source.write(script_content)
                    source_path = Path(source.name)
                try:
                    functions = parser.parse_file(source_path)
                finally:
                    source_path.unlink(missing_ok=True)
                for function in functions:
                    start_pos = function["start"]
                    end_pos = function["end"]
                    function_id = f"{request_url} | {start_pos} | {end_pos}"
                    self.function_id_map[request_url].add(function_id)
                    self.function_metadata_map[request_url][function_id] = function
                self.__add_log_statements_to_update_file(request_url, functions)
            except Exception as error:
                self.instrumentation_errors[request_url] = str(error)
                print("Fail-closed instrumentation skip", request_url, error)


    def __add_log_statements_to_update_file(self, request_url: str, functions: list) -> None:
        """Add one global marker call to every parsed function body.

        A shared in-memory set limits each function identifier to one console message.
        Block bodies retain directive prologues. Concise arrow expressions are wrapped
        in a sequence expression so their return value remains unchanged.
        """
        bootstrap = (
            ";globalThis.__muzeelUsedFunctions??=new Set;"
            "globalThis.__muzeelMark??=function(i){"
            "if(!globalThis.__muzeelUsedFunctions.has(i)){"
            "globalThis.__muzeelUsedFunctions.add(i);console.log(i)}};"
        )
        edits = []
        for function in functions:
            start_pos = function["start"]
            end_pos = function["end"]
            function_id = f"{request_url} | {start_pos} | {end_pos}"
            marker = f";globalThis.__muzeelMark({function_id!r});"
            if function["body_kind"] == "block":
                edits.append((function["marker_offset"], function["marker_offset"], marker))
            else:
                edits.append((start_pos, start_pos, f"(globalThis.__muzeelMark({function_id!r}),"))
                edits.append((end_pos + 1, end_pos + 1, ")"))
        updated = self.data_map[request_url]["updated"]
        for start_pos, end_pos, replacement in sorted(edits, reverse=True):
            updated = updated[:start_pos] + replacement + updated[end_pos:]
        self.data_map[request_url]["updated"] = bootstrap + updated

    def remove_unused_functions(self, used_function_id_map: dict):
        """This removes unused functions from a javascript file.
        It received a map of used functions of the form {request_url: set(used_function_ids)}
        From this map, it generates a list of unused functions. Nested functions are removed from this list first, to enable easy elimination.
        functions in the using __remove_functions
        """
        unused_function_id_map = EliminationUtils.determine_unused_functions(self.function_id_map, used_function_id_map)
        for request_url in unused_function_id_map:
            unused_ids = unused_function_id_map[request_url]
            metadata = self.function_metadata_map.get(request_url, {})
            candidates = [metadata[function_id] for function_id in unused_ids if function_id in metadata]
            candidates.sort(key=lambda row: (row["start"], -row["end"]))
            outermost = []
            for candidate in candidates:
                if outermost and candidate["end"] <= outermost[-1]["end"]:
                    continue
                outermost.append(candidate)
            self.__remove_functions(request_url, outermost)

    def __remove_functions(self, request_url: str, functions: list):
        """Empty unused outer function bodies while retaining valid syntax."""
        script_content = self.data_map[request_url]["original"]
        for function in sorted(functions, key=lambda row: row["start"], reverse=True):
            start_pos = function["start"]
            end_pos = function["end"]
            if function["body_kind"] == "block":
                script_content = script_content[:start_pos + 1] + script_content[end_pos:]
            else:
                script_content = script_content[:start_pos] + "void 0" + script_content[end_pos + 1:]

        if not os.path.exists(f'ranges/{self.url.replace("/", "_")}/'):
            os.makedirs(f'ranges/{self.url.replace("/", "_")}/')

        #print (self.request_url_content_file_map[request_url])
        content_file_path = self.request_url_content_file_map[request_url]
        range_file_path = content_file_path.replace(".c", ".txt")

        with open(f'ranges/{self.url.replace("/", "_")}/{range_file_path}', 'w') as f:
            for function in functions:
                f.write(
                    f"{function['start']},{function['end']},{function['body_kind']}\n"
                )

        self.data_map[request_url]["updated"] = script_content

    def persist_updated_files(self):
        """This saves the updated content to disk with the ".m" extension.
        """
        for request_url in self.data_map:
            content_file_path = self.request_url_content_file_map[request_url]
            update_file_path = content_file_path.split(".c")[0] + ".m"
            with open(self.cache_directory + "/" + "muzeel" + "/" + update_file_path, "w") as update_file:
                update_file.write(self.data_map[request_url]["updated"])
