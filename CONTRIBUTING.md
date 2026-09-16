# Muzeel AI Agent 연구 기여 방법

이 저장소는 원본 Muzeel의 구조를 유지하면서 상태 기반 웹 탐색과 안전한
JavaScript 제거를 연구한다. 코드 감소량보다 재현 가능한 증거와 기능 보존을
우선한다.

## 시작하기

1. 작업 목적과 평가 방법을 이슈에 먼저 적는다.
2. 현재 브랜치에서 기능 브랜치를 만든다.
3. 코드와 실험 데이터와 설명 문서를 함께 수정한다.
4. 필수 검증 명령을 실행한다.
5. 확인한 결과와 확인하지 못한 범위를 Pull Request에 적는다.

원본 저장소에는 별도 라이선스 파일이 없다. 이 포크도 새로운 라이선스를
임의로 선언하지 않는다. 외부 코드와 논문 원문과 웹사이트 응답을 복사하기 전에
재배포 권한을 확인해야 한다.

## 연구 제안에 필요한 내용

- 해결하려는 Muzeel의 구체적인 한계
- 비교 대상과 통제 조건
- 행동 횟수와 시간 예산
- 수집할 지표와 성공 기준
- 기능 손상을 확인할 독립 시나리오
- 개인정보와 대상 사이트 코드를 공개하지 않는 방법
- 결과를 일반화할 수 없는 조건

AI를 사용했다는 사실만으로 연구 기여가 되지는 않는다. 규칙 기반 방법으로도
같은 결과를 얻을 수 있는지 비교해야 한다.

## 공개하면 안 되는 자료

- 대상 사이트의 JavaScript 원문과 HTML 응답 원문
- 쿠키와 인증 토큰과 브라우저 프로필
- 사용자의 입력값과 개인정보
- API 키와 모델 인증 정보
- 익명화하지 않은 원본 화면 추적
- 재배포 권한이 없는 논문과 그림과 번역 전문

공개 데이터에는 해시와 크기와 개수와 범주화된 오류를 우선 사용한다.

## 실험 데이터 규칙

실험마다 실행 환경과 대상 범위와 커밋과 예산과 실패 기록을 남긴다. 성공한
결과만 남기지 않는다. 공격적 처리 결과와 최종 채택 결과를 구분한다.

상태 기반 탐색 데이터는
[`experiments/state-aware-exploration`](experiments/state-aware-exploration/README.md)의
형식을 따른다. 예시 데이터는 실제 사이트의 DOM과 코드를 포함하지 않는다.

## 필수 검증

```sh
npm install
python3 -m unittest discover -s tests -v
python3 -m unittest -v test_modern_parser.py test_modern_datastore.py
python3 experiments/solid-connection/validate_dataset.py
python3 experiments/state-aware-exploration/validate_transition.py \
  experiments/state-aware-exploration/transition.example.json
node --check modern_js_functions.mjs
```

브라우저 실행기를 수정했다면 로컬 스냅샷에서 새 추적을 만들고 탐색에 사용하지
않은 시나리오로 원본과 처리본을 비교해야 한다.

## Pull Request 작성 기준

- 변경 목적과 연구 질문을 설명한다.
- 직접 실행한 명령과 결과를 적는다.
- 실패와 제한 사항을 숨기지 않는다.
- 성능 수치는 원본과 처리본의 같은 조건을 비교한다.
- 기능 보존 주장은 실제로 실행한 시나리오 범위로 제한한다.
- 생성형 AI를 사용한 경우 작성과 코드와 실험 중 어디에 사용했는지 적는다.
