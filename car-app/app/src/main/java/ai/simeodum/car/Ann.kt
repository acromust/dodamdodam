package ai.simeodum.car

/**
 * 차 안내 녹음(75번 B-2, 11/10 사용자 결정). 이름·순간·숫자를 넣지 않은 고정 문장만 쓴다.
 * 파일은 res/raw/<raw>.m4a(제미나이 TTS gemini-2.5-flash-preview-tts로 만든다: car-app/tools/make_ann.py).
 * 파일이 없으면 띵동만 나온다(기기 TTS로 대신 읽지 않는다).
 */
enum class Ann(val raw: String, val text: String) {
    /** 그날 첫 출발, 예약된 메시지가 있을 때(띵동 없음). */
    DEPART("ann_depart", "예약된 음성 메시지가 있습니다."),
    /** 운행에서 처음 알릴 때(주행 중·정차 중 알림 모두). */
    ARRIVE_FIRST("ann_arrive_first", "음성 메시지가 도착했습니다. 들으시려면 핸들 가운데 버튼을 눌러 주세요."),
    /** 같은 운행의 두 번째부터 · 자동 재생 · 주차해서 바로 틀 때. */
    ARRIVE("ann_arrive", "음성 메시지가 도착했습니다."),
    /** 주차했는데 도착한 메시지가 2개 이상(화면 목록에서 고른다) · 주행 집중 모드로 주차해서 이어 들을 때. */
    PARKED("ann_parked", "도착한 음성 메시지가 있습니다."),
}
