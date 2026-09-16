# 상태 기반 탐색 공개 데이터 형식

이 디렉터리는 브라우저 행동과 새 화면 상태와 동적 JavaScript 청크를 연결하는
공개 데이터 형식을 정의한다. 현재 포함된 JSON은 형식을 설명하기 위한 가상
예시이며 실제 사이트 실험 결과가 아니다.

## 전이 한 건이 나타내는 것

전이 한 건은 다음 순서를 기록한다.

1. 행동 전 화면 상태를 해시로 식별한다.
2. Agent 또는 규칙 기반 탐색기가 제안한 행동을 기록한다.
3. 정책 검증 결과와 실제 실행 결과를 기록한다.
4. 행동 후 상태와 새 인터랙션 수를 기록한다.
5. 행동으로 새로 발생한 네트워크 요청과 JavaScript 청크를 기록한다.
6. 계측 재실행에서 늘어난 함수 실행 수를 기록한다.

## 공개 데이터 보호

DOM과 JavaScript 본문과 쿠키와 인증 값은 기록하지 않는다. 실제 주소와
선택자가 연구 공개에 필요하지 않으면 해시 또는 익명 식별자로 대체한다.
`javascript_source`, `html`, `dom`, `cookie`, `token`이라는 키가 포함된 데이터는
검증기가 거부한다.

## 파일

| 파일 | 설명 |
| --- | --- |
| `transition.schema.json` | 전이 JSON Schema |
| `transition.example.json` | 모달 열기 전이의 가상 예시 |
| `validate_transition.py` | 필수 필드와 수치 및 민감 키 검사 |

## 검증

```sh
python3 experiments/state-aware-exploration/validate_transition.py \
  experiments/state-aware-exploration/transition.example.json
```

정상 데이터는 `transition dataset: valid`를 출력한다.

## 실제 실험을 추가할 때

실행 날짜와 Muzeel 커밋과 탐색 방식과 행동 예산과 시간 예산을 함께 기록한다.
원본과 규칙 기반 재탐색과 AI Agent 재탐색은 같은 예산을 사용해야 한다. 새
청크를 발견했지만 계측 재실행을 하지 못한 경우 `discovered` 상태로 남기며 함수
커버리지에 포함하지 않는다.
