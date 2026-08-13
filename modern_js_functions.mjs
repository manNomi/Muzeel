#!/usr/bin/env node

import fs from "node:fs";
import { parse } from "@babel/parser";

const FUNCTION_TYPES = new Set([
  "ArrowFunctionExpression",
  "ClassMethod",
  "ClassPrivateMethod",
  "FunctionDeclaration",
  "FunctionExpression",
  "ObjectMethod",
]);

function parseModernJavaScript(source) {
  const common = {
    allowAwaitOutsideFunction: true,
    allowImportExportEverywhere: true,
    allowNewTargetOutsideFunction: true,
    allowReturnOutsideFunction: true,
    errorRecovery: false,
    sourceType: "unambiguous",
  };
  const attempts = [
    ["jsx", "decorators-legacy"],
    ["typescript", "jsx", "decorators-legacy"],
    ["flow", "jsx", "decorators-legacy"],
  ];
  const errors = [];
  for (const plugins of attempts) {
    try {
      return parse(source, { ...common, plugins });
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
    }
  }
  throw new Error(errors.join(" | "));
}

function utf16ToCodePointMap(source) {
  const offsets = new Uint32Array(source.length + 1);
  let codePointOffset = 0;
  for (let index = 0; index < source.length; index += 1) {
    offsets[index] = codePointOffset;
    const value = source.codePointAt(index);
    if (value > 0xffff) {
      index += 1;
      offsets[index] = codePointOffset;
    }
    codePointOffset += 1;
  }
  offsets[source.length] = codePointOffset;
  return offsets;
}

function collectFunctions(ast, source) {
  const offsets = utf16ToCodePointMap(source);
  const functions = [];

  function visit(value) {
    if (!value || typeof value !== "object") return;
    if (Array.isArray(value)) {
      for (const item of value) visit(item);
      return;
    }
    if (FUNCTION_TYPES.has(value.type) && value.body) {
      const body = value.body;
      const block = body.type === "BlockStatement";
      let markerOffset = body.start;
      if (block) {
        markerOffset += 1;
        const directives = Array.isArray(body.directives) ? body.directives : [];
        if (directives.length > 0) {
          markerOffset = directives[directives.length - 1].end;
        }
      }
      functions.push({
        function_type: value.type,
        body_kind: block ? "block" : "expression",
        start: offsets[body.start],
        end: offsets[body.end] - 1,
        marker_offset: offsets[markerOffset],
      });
    }
    for (const [key, child] of Object.entries(value)) {
      if (["comments", "errors", "extra", "loc", "tokens"].includes(key)) continue;
      visit(child);
    }
  }

  visit(ast.program);
  functions.sort((left, right) => left.start - right.start || right.end - left.end);
  return functions;
}

function main() {
  const file = process.argv[2];
  if (!file) throw new Error("usage: modern_js_functions.mjs <javascript-file>");
  const source = fs.readFileSync(file, "utf8");
  const ast = parseModernJavaScript(source);
  process.stdout.write(JSON.stringify({ functions: collectFunctions(ast, source) }));
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 1;
}
