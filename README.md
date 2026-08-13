# Muzeel: Assessing the impact of JavaScript dead code elimination on mobile web performance

> 이 포크는 최신 JavaScript 파서와 브라우저 에이전트 기반 탐색을 실험한
> 개선판입니다. 원본 프로젝트의 구조와 커밋 이력을 유지합니다.

## 개선판 문서

- [구조와 구현 방법](docs/architecture-ko.md)
- [Solid Connection 실험 보고서](docs/solid-connection-case-study-ko.md)
- [공개 데이터 설명과 검증 방법](experiments/solid-connection/README.md)

Solid Connection 홈 화면 사례에서 최종 안전 정책은 JavaScript를
1,919,566바이트에서 1,481,143바이트로 줄였습니다. 감소율은 22.84%입니다.
브라우저 에이전트가 확인한 상호작용 13개를 재생했고 별도로 분리한 회귀
시나리오 다섯 개가 모두 통과했습니다. 이 수치는 홈 화면과 공개된 검증
범위에만 해당하며 전체 사이트의 안전성을 보장하지 않습니다.

Muzeel is a framework for the identification and elimination of unused JavaScript functions, also known as "deadcode". It is a black-box approach requiring neither knowledge of the code nor execution traces. The core design principle of Muzeel is to address the challenge of dynamically analyzing JavaScript after the page is loaded, by emulating all possible user interactions with the page, such that the used functions (executed when interactivity events fire) are accurately identified, whereas unused functions are filtered out and eliminated.

## Paper
You can find the paper [here].
You can watch the presentation of Muzeel on this [video].

## Instructions

Install MySQL and an easy GUI that will allow you to access the DB, e.g., phpMyAdmin (Ubuntu), or DBeaver (MacOS).

Import the DB template "templateDB.sql" into your MySQL under the DB name "muzeel". This 
should create a table called "cachedPages" with various columns.

### Create the list of sites

Inside the "sites_lists" folder you can create a text file of the sites that you are interested in running Muzeel on. In principle one can create multiple lists if you intend to run them in parallel to speed things up. Make sure that each site URL is on a separate line, and each site URL ends with a "/".


### Update Muzeel configurations

Edit the config.py file to reflect the configurations that you have chosen. There are five main parameters to configure: 1) DB name, 2) MySQL username, 3) MySQL password, 4) Full path to the Muzeel git repo, and 5) the MySQL port number (default 3306).

### Install dependencies
pip3 install mitmdump esprima selenium-wire pymysql==0.10.1 markupsafe==1.1.0

The improved instrumentation path also requires the modern JavaScript parser:

```sh
npm install
python3 -m unittest -v test_modern_parser.py test_modern_datastore.py
```

The parser bridge supports current syntax such as optional chaining, nullish
coalescing, arrow functions, and class or object methods. A file that cannot be
parsed is left unchanged. This fail-closed behavior prevents partial function
maps from being treated as complete dead-code evidence.

Cross-origin scripts are also preserved by default. Interaction coverage from a
single page is not a sound basis for rewriting independently deployed analytics,
authentication, monitoring, or widget code.

Bundles containing a protected runtime marker are preserved as well. The
default marker protects Sentry initialization because changing application-side
monitoring setup can break an otherwise untouched cross-origin monitoring SDK.
Callers can provide `protected_content_markers` in `db_details` to adapt this
allowlist for a site.

### Clone the sites 

In a separate terminal run the caching proxy as:
````` sh
cd muzeel/proxies/
mitmdump -s cache_proxy.py --set block_global=false --ssl-insecure --set upstream-cert=false --listen-port 9701
`````

Make sure that the proxy is not throwing any errors and that it is showing the following message "Proxy server listening at http://*:9701"

Now, in a separate terminal, run the scraper code as:
````` sh
cd muzeel
python3 scraper.py 9701 sites_lists/site_list_1
`````

This should go over the list of sites that are listed in site_list_1, and then opens each page in chrome while scrolling through the site. At the end you should be able to see several entries in the DB, as well as seeing multiple files inside the data folder (with .c, .h, and .u extensions).


### Running Muzeel to eliminate deadcode

In a separate terminal run the caching proxy as:
````` sh
cd muzeel/proxies/
mitmdump -s read_proxy.py --set block_global=false --ssl-insecure --set upstream-cert=false --listen-port 9700
`````

Make sure that the proxy is not throwing any errors and that it is showing the following message "Proxy server listening at http://*:9700"

Now, in a separate terminal, run the scraper code as:
````` sh
cd muzeel
python3 run_test.py site_list_1 9700
`````

By the end of this, you should be able to see the deadcode eliminated JavaScript files stored inside /data/muzeel, each with a .m extension.

[here]: <https://dl.acm.org/doi/10.1145/3517745.3561427>
[video]: <https://iframe.videodelivery.net/eyJraWQiOiI3YjgzNTg3NDZlNWJmNDM0MjY5YzEwZTYwMDg0ZjViYiIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiJlZDI0ZTFlYjQ3NGQwMjA4NmQ3ZWZkYTc5NGNlMGQzMSIsImtpZCI6IjdiODM1ODc0NmU1YmY0MzQyNjljMTBlNjAwODRmNWJiIiwiZXhwIjoxNjcyODQ1NzU0fQ.a39D0zQ4eIy4ObEF6RQIh4tCIgaiv4zjjV3aGNarL0h-HoFXUJVkSgpkSRSzhaAHxFB7k8oCAcuAE-rOYm-1JpvC2AkkqRXS1G0N-a7i9r--a3oAl0q-H-WpPlAkPafq7mUdbiTh3AL-Wgwi3FaKpuLKlzemvHUtITC3D9WiNkhWcobXkzNzRATOonVHFIw1zjUWdTDkODZjLzxozyZonmsjiiCYVB31nlqK1zf9TpcBw7Beitcv1Ri0LTeNjQRFEXGm9pjHu8MZBRglbq1wfzTrFs33gy-Ox94bmylOZx5FgWIha_yFKxHcCIiCfm1q8rWHOwvQMcYEytnM7k6HPg>
