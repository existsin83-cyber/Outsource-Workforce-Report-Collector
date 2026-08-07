"""익명화된 실 메일 본문 픽스처.

주의: 회사 DRM/보안 에이전트가 순수 텍스트(.txt) 파일의 읽기를 가로채는 현상이
확인되어(같은 내용도 .py 확장자면 정상 처리됨) 픽스처를 파일이 아닌 파이썬 문자열
상수로 둔다.
"""

FORMAT_A_CATEGORY_DOT = """\
안녕하십니까. 홍길동 입니다.

26년 07월 23일 PCB 개인 업무 보고 드립니다.

-CO2-

.고객사A Edge_Skiver ABC-200 #2,#3

.수주번호 : XX260301 , XX260302

.출하 : 9/16

.전장 제작 진행중(안산공장)

.고객사B ABC-400 ABF Shaving #2 1대

.수주번호 : ZZ260321

.외주 인원 : 1명 (야근 : 1명) [총 공수 : 43.5 MD]

.전장 제작 진행중(안산공장)

.고객사C CO2 DRILLER XYZ-200 #4, #5 2대

.수주번호 : XX260310, XX260401

.출하 8/20 ->8/28

.외주 인원 : 0명 (야근 0명) [총 공수 : 55.5MD]

.사업부 이관

이상입니다.
홍길동 드림.
"""

FORMAT_B_NUMBERED_VENDOR_PER_UNIT = """\
안녕하십니까

김철수 프로입니다.

7월 24일 금요일 일일 업무보고 드립니다.

1. 고객사D 모델X#7~#8 (청주)

.수주번호 : MK260307, ZZ260317(MK260404) - #7호기(M15), #8호기(M12)

. #7호기 사업부 이관 완료(7/9)

. #8호기 전장 대조립 진행중 (40%)

. 외주인원 – 협력사A

- #7호기 : 누적공수 : 18.5공수

- #8호기 : 주간 4 야간 0 누적공수 : 9공수

2. 고객사E 모델Y#1~5

.수주번호 : ME260501~5

.외주인원 – 협력사B

- 1호기 : 주간 5, 야간 3, 누적공수 : 35공수

- 2호기 : 주간 4, 야간 4, 누적공수 : 35공수

이상입니다.
김철수 드림
"""

FORMAT_C_INLINE_ALL_IN_ONE_LINE = """\
안녕하십니까. 이영희입니다.
2026.07.24 업무보고드립니다.

1. 고객사F 모델Z #18~23

  수주번호 : ZZ260203~260207, ZZ260403 외주인원 : 6명 (야근 : 6명)

  Stage 입고 일정 : #18 5/22, #19 5/29

  -.전장작업 진행중 (90%)

2. 고객사G 모델W

  수주번호 : ZZ260202

  -.전장작업 진행중 (90%)

이상입니다.
감사합니다.
"""

FORMAT_D_INLINE_REPORTED_DAILY = """\
2026년 7월 27일 업무보고입니다.

1. 고객사H 장비Alpha #1
.수주번호 : AA260101
.외주 인원 : 1 명 (야근: 1 명 투입 공수 : 1.5)

2. 고객사I 장비Beta #2
.수주번호 : BB260202
.외주 인원 : 3 명 (야근: 1 명 투입 공수 : 3.5)
"""

# Bare equipment headers with no numbered/dot prefix. This is an anonymized
# regression shape: a single numbered category line is followed by equipment
# names ending in a unit count, then dot-prefixed detail fields.
FORMAT_E_BARE_EQUIPMENT_MAN_DAY = """\
1. PCB & PKG
SI Flex UV Driller 4500U 10대
.수주번호 : SK260404~13
.Frame 입고 : 6/9 (4대), 6/16 (6대)
.출하 일정 : 8/6 (4대), 8/13 (6대)
.공수 : [총 공수 : 119.5MD]
.전장
- 케이블 베어 커버 부착 미스로 인하여 재작업
DNP UV Driller 4000U 7대
.수주번호 : DN260404~10
.공수 : 주간 6명, 야간 6 [총 공수 : 50.5]
SEMV 2.0 3대
.수주번호 : SM260404~06
.공수 : [총 공수 : 33.5MD]
SEMV 1.5 2대
.수주번호 : SM260407~08
.공수 : [총 공수 : 29.0MD]
"""

# Parser regression inputs. Keep these anonymized as Python strings because
# local DRM tooling can interfere with standalone text fixtures.
CUMULATIVE_MAN_DAY_VARIANTS = (
    ("누적 공수 : 9", 9.0),
    ("누적 공수: 9 MD", 9.0),
    ("누적 공수 : 18.5공수", 18.5),
)

TOTAL_INPUT_MAN_DAY = "외주 인원 : 1명 (야근 : 0명) 총 투입 공수 : 100"
TOTAL_AND_DAILY_MAN_DAY = "외주 인원 : 1명 총  투입 공수 : 100\n투입 공수 : 2"
INLINE_HEADCOUNT_WITH_CUMULATIVE = "외주 인원 : 2명 (야근 2명) 누적 공수 : 73.5공수"

DATE_SUBJECT_UNDERSCORE = "26_07_29 (수) 일일 업무보고"
DATE_SUBJECT_DOTTED = "2026. 07. 29. 외주 작업보고"
DATE_SUBJECT_KOREAN = "7월 29일 일일 업무보고"
DATE_BODY_MATCHING = "2026년 7월 29일 업무보고 드립니다."
DATE_BODY_CONFLICTING = "2026년 7월 28일 업무보고 드립니다."

# 장비 구간 안에 작업일과 무관한 날짜(입고/출하 예정일 등)가 있는 실제 관찰 패턴.
# 본문 전체를 날짜 탐색 대상으로 삼으면 이 날짜가 DATE_MISMATCH 오탐을 일으킨다.
DATE_BODY_UNRELATED_DATE_IN_EQUIPMENT_SECTION = (
    "안녕하세요, 일일 업무 보고 드립니다.\n"
    "4. LAton58호기\n"
    ".수주번호 : ZZ260116\n"
    ".외주 인원 : 2명 (야근 2명) 누적 공수 : 76.5공수\n"
    ".Stage & Frame : 2026-07-10 입고 완료\n"
    ".출하 : 2026-09-20 예정"
)
