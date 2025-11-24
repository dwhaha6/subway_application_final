"""
지하철 좌석 예측 앱 - 메인 애플리케이션
모바일 친화적 UI + 실시간 API 연동
"""
from flask import Flask, render_template, request, jsonify, session
from api.seoul_api import SeoulSubwayAPI, MockSeoulSubwayAPI
from api.sk_api import SKCongestionAPI
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

# API 키 설정
SEOUL_API_KEY = '6374426278647768383058726c6572'

# API 초기화
try:
    seoul_api = SeoulSubwayAPI(SEOUL_API_KEY)
    print("[OK] 서울 실시간 도착 API 연동 완료")
except Exception as e:
    print(f"[WARNING] 서울 API 초기화 실패, Mock API 사용: {e}")
    seoul_api = MockSeoulSubwayAPI()

# 칸별 혼잡도 (통계 기반 추론)
sk_api = SKCongestionAPI()
print("[OK] 칸별 혼잡도 통계 기반 추론 시스템 활성화")

# 서울 지하철 노선 데이터 (간소화)
SUBWAY_LINES = {
    "2호선": {
        "stations": ["시청", "을지로입구", "을지로3가", "을지로4가", "동대문역사문화공원",
                    "신당", "상왕십리", "왕십리", "한양대", "뚝섬", "성수", "건대입구",
                    "구의", "강변", "잠실나루", "잠실", "삼성", "선릉", "역삼", "강남",
                    "교대", "서초", "방배", "사당", "낙성대", "서울대입구", "봉천", "신림",
                    "신대방", "구로디지털단지", "대림", "신도림", "문래", "영등포구청",
                    "당산", "합정", "홍대입구", "신촌", "이대", "아현", "충정로"],
        "color": "#00A84D"
    }
}

# 역 좌표 데이터 (주요 역만 - 실제로는 전체 역 필요)
STATION_COORDS = {
    "강남": {"lat": 37.4979, "lng": 127.0276},
    "역삼": {"lat": 37.5007, "lng": 127.0365},
    "선릉": {"lat": 37.5048, "lng": 127.0495},
    "삼성": {"lat": 37.5088, "lng": 127.0633},
    "잠실": {"lat": 37.5133, "lng": 127.1001},
    "건대입구": {"lat": 37.5404, "lng": 127.0703},
    "왕십리": {"lat": 37.5613, "lng": 127.0374},
    "신당": {"lat": 37.5661, "lng": 127.0176},
    "시청": {"lat": 37.5665, "lng": 126.9780},
    "홍대입구": {"lat": 37.5573, "lng": 126.9236},
    "신도림": {"lat": 37.5088, "lng": 126.8913},
}


@app.route('/')
def index():
    """메인 화면 - 출발/도착역 선택"""
    return render_template('index.html', lines=SUBWAY_LINES)


@app.route('/test-map')
def test_map():
    """Kakao Map 테스트 페이지"""
    return render_template('test_map.html')


@app.route('/api/arrivals/<station>')
def get_arrivals(station):
    """특정 역의 실시간 도착 정보 API"""
    arrivals = seoul_api.get_realtime_arrival(station)
    return jsonify(arrivals)


@app.route('/api/congestion/<line>/<station>/<direction>')
def get_congestion(line, station, direction):
    """특정 역/노선의 칸별 혼잡도 API"""
    congestion = sk_api.get_car_congestion(line, station, direction)
    return jsonify(congestion)


@app.route('/api/station-coords/<station>')
def get_station_coords(station):
    """역 좌표 정보 API"""
    coords = STATION_COORDS.get(station)
    if coords:
        return jsonify(coords)
    return jsonify({"error": "Station not found"}), 404


@app.route('/journey')
def journey():
    """여정 화면 - 지도 + 열차 선택 + 칸 선택 + 실시간 정보"""
    start_station = request.args.get('start')
    end_station = request.args.get('end')
    line = request.args.get('line', '2호선')

    if not start_station or not end_station:
        return "출발역과 도착역을 선택해주세요", 400

    # 세션에 여정 정보 저장
    session['start_station'] = start_station
    session['end_station'] = end_station
    session['line'] = line

    return render_template('journey.html',
                         start_station=start_station,
                         end_station=end_station,
                         line=line,
                         start_coords=STATION_COORDS.get(start_station, {}),
                         end_coords=STATION_COORDS.get(end_station, {}))


@app.route('/api/select-train', methods=['POST'])
def select_train():
    """사용자가 탈 열차 선택"""
    data = request.json
    session['selected_train'] = data.get('train_no')
    session['arrival_time'] = data.get('arrival_time')
    session['train_direction'] = data.get('direction')

    return jsonify({"status": "ok"})


@app.route('/api/select-car', methods=['POST'])
def select_car():
    """사용자가 탈 칸 선택 (선택사항)"""
    data = request.json
    session['selected_car'] = data.get('car_no')
    session['boarded'] = False  # 아직 탑승 전

    return jsonify({"status": "ok", "message": "칸 정보가 저장되었습니다!"})


@app.route('/riding')
def riding():
    """탑승 중 화면 - 실시간 위치 및 하차 예측"""
    start_station = session.get('start_station')
    end_station = session.get('end_station')
    line = session.get('line', '2호선')
    selected_car = session.get('selected_car')

    if not start_station or not end_station:
        return "세션이 만료되었습니다", 400

    # 출발역부터 도착역까지의 역 리스트 생성
    stations = SUBWAY_LINES[line]['stations']
    try:
        start_idx = stations.index(start_station)
        end_idx = stations.index(end_station)

        if start_idx < end_idx:
            route_stations = stations[start_idx:end_idx+1]
        else:
            route_stations = stations[end_idx:start_idx+1]
            route_stations.reverse()
    except ValueError:
        route_stations = [start_station, end_station]

    return render_template('riding.html',
                         start_station=start_station,
                         end_station=end_station,
                         line=line,
                         selected_car=selected_car,
                         stations=route_stations)


@app.route('/api/board-train', methods=['POST'])
def board_train():
    """열차 탑승 처리 (출발역 도착 시 자동 호출)"""
    session['boarded'] = True
    session['current_station'] = session.get('start_station')

    # 좌석 정보 초기화
    if session.get('selected_car'):
        seats = _generate_seat_data(
            session.get('start_station'),
            session.get('end_station'),
            session.get('line', '2호선')
        )
        session['seats'] = seats

    return jsonify({
        "status": "ok",
        "message": "열차에 탑승하셨습니다!",
        "show_exit_prediction": session.get('selected_car') is not None,
        "redirect": "/riding"
    })


@app.route('/api/next-station', methods=['POST'])
def next_station():
    """다음 역 도착 처리"""
    current = session.get('current_station')
    end = session.get('end_station')
    line = session.get('line', '2호선')

    stations = SUBWAY_LINES[line]['stations']

    try:
        current_idx = stations.index(current)
        end_idx = stations.index(end)

        # 다음 역으로 이동
        if current_idx < end_idx:
            next_station = stations[current_idx + 1]
        else:
            next_station = stations[current_idx - 1]

        session['current_station'] = next_station

        # 도착역 체크
        if next_station == end:
            session['arrived'] = True
            return jsonify({
                "status": "arrived",
                "message": f"{end}역에 도착했습니다!",
                "station": next_station
            })

        # 하차 예측 정보 생성
        exit_prediction = _generate_exit_prediction(session.get('selected_car', 1))

        return jsonify({
            "status": "ok",
            "station": next_station,
            "exit_prediction": exit_prediction
        })

    except ValueError:
        return jsonify({"error": "Invalid station"}), 400


def _generate_seat_data(start_station, end_station, line):
    """
    좌석별 하차 예정 정보 생성 (앱 사용자 시뮬레이션)

    14개 좌석 각각에 대해:
    - 빈 좌석 or 앉은 사람
    - 앱 사용자 여부
    - 하차 예정역
    """
    import random

    # 경로 상의 모든 역 리스트
    stations = SUBWAY_LINES[line]['stations']
    start_idx = stations.index(start_station)
    end_idx = stations.index(end_station)

    if start_idx < end_idx:
        route_stations = stations[start_idx:end_idx+1]
    else:
        route_stations = stations[end_idx:start_idx+1]
        route_stations.reverse()

    seats = []
    for seat_no in range(1, 15):  # 14개 좌석
        # 70% 확률로 누군가 앉아있음
        if random.random() < 0.7:
            # 앉아있는 경우
            is_app_user = random.random() < 0.6  # 60%가 앱 사용자

            if is_app_user:
                # 앱 사용자는 하차 예정역을 알 수 있음
                # 현재역 이후의 역 중 랜덤 선택
                if len(route_stations) > 1:
                    exit_station = random.choice(route_stations[1:])
                else:
                    exit_station = end_station

                seats.append({
                    'seat_no': seat_no,
                    'occupied': True,
                    'is_app_user': True,
                    'exit_station': exit_station,
                    'is_current_user': False,
                    'waiters': random.randint(0, 2)  # 대기자 수
                })
            else:
                # 일반 사용자는 하차 예정역을 알 수 없음
                seats.append({
                    'seat_no': seat_no,
                    'occupied': True,
                    'is_app_user': False,
                    'exit_station': None,
                    'is_current_user': False,
                    'waiters': random.randint(0, 2)
                })
        else:
            # 빈 좌석
            seats.append({
                'seat_no': seat_no,
                'occupied': False,
                'is_app_user': False,
                'exit_station': None,
                'is_current_user': False,
                'waiters': 0
            })

    return seats


def _generate_exit_prediction(car_no):
    """
    하차 예측 정보 생성

    혼잡도 기반 예상 하차 인원 + 앱 사용자 확정 하차 인원
    """
    import random

    # 혼잡도 기반 예상 하차 (3-12명)
    estimated_exits = random.randint(3, 12)

    # 앱 사용자 확정 하차 (1-4명)
    app_user_exits = random.randint(1, 4)

    # 확률 계산 (앱 사용자 비율 60%)
    total_in_car = random.randint(20, 30)
    exit_probability = (estimated_exits / total_in_car) * 100

    return {
        "estimated_exits": estimated_exits,
        "app_user_exits": app_user_exits,
        "total_in_car": total_in_car,
        "exit_probability": round(exit_probability, 1),
        "message": f"이번 역에서 약 {estimated_exits}명 하차 예상 (확정 {app_user_exits}명)"
    }


@app.route('/api/seats')
def get_seats():
    """현재 칸의 좌석 정보 조회"""
    seats = session.get('seats', [])
    current_station = session.get('current_station')

    return jsonify({
        "status": "ok",
        "seats": seats,
        "current_station": current_station
    })


@app.route('/api/update-seats', methods=['POST'])
def update_seats():
    """역 통과 시 좌석 상태 업데이트"""
    current_station = request.json.get('current_station')
    seats = session.get('seats', [])

    # 해당 역에서 내릴 사람들의 좌석을 비움
    updated_seats = []
    for seat in seats:
        if seat['occupied'] and seat['exit_station'] == current_station:
            # 이 역에서 하차 -> 좌석 비움
            # 단, 현재 사용자가 앉은 좌석이면 유지
            if seat.get('is_current_user'):
                updated_seats.append(seat)
            else:
                # 대기자가 있으면 대기자 중 한 명이 앉음
                if seat.get('waiters', 0) > 0:
                    import random
                    updated_seats.append({
                        'seat_no': seat['seat_no'],
                        'occupied': True,
                        'is_app_user': random.random() < 0.6,
                        'exit_station': None,  # 새로 탄 사람은 아직 목적지 미정
                        'is_current_user': False,
                        'waiters': seat['waiters'] - 1
                    })
                else:
                    updated_seats.append({
                        'seat_no': seat['seat_no'],
                        'occupied': False,
                        'is_app_user': False,
                        'exit_station': None,
                        'is_current_user': False,
                        'waiters': 0
                    })
        else:
            updated_seats.append(seat)

    session['seats'] = updated_seats

    return jsonify({
        "status": "ok",
        "seats": updated_seats
    })


@app.route('/api/sit-seat', methods=['POST'])
def sit_seat():
    """좌석에 앉기"""
    seat_no = request.json.get('seat_no')
    seats = session.get('seats', [])

    # 이미 사용자가 앉아있는 좌석이 있는지 확인
    for seat in seats:
        if seat.get('is_current_user', False):
            return jsonify({"status": "error", "message": "이미 다른 좌석에 앉아있습니다"}), 400

    updated_seats = []
    for seat in seats:
        if seat['seat_no'] == seat_no:
            if not seat['occupied']:
                # 빈 좌석이면 앉기
                updated_seats.append({
                    'seat_no': seat_no,
                    'occupied': True,
                    'is_app_user': True,
                    'exit_station': session.get('end_station'),
                    'is_current_user': True,
                    'waiters': seat.get('waiters', 0)
                })
            else:
                # 이미 누가 앉아있으면 실패
                return jsonify({"status": "error", "message": "이미 사람이 앉아있습니다"}), 400
        else:
            updated_seats.append(seat)

    session['seats'] = updated_seats

    return jsonify({
        "status": "ok",
        "message": "좌석에 앉았습니다!",
        "seats": updated_seats
    })


@app.route('/api/wait-seat', methods=['POST'])
def wait_seat():
    """좌석 앞에서 대기하기"""
    seat_no = request.json.get('seat_no')
    seats = session.get('seats', [])

    updated_seats = []
    for seat in seats:
        if seat['seat_no'] == seat_no:
            # 대기자 수 증가
            updated_seats.append({
                **seat,
                'waiters': seat.get('waiters', 0) + 1
            })
        else:
            updated_seats.append(seat)

    session['seats'] = updated_seats

    return jsonify({
        "status": "ok",
        "message": f"{seat_no}번 좌석 대기 중",
        "seats": updated_seats
    })


@app.route('/reset')
def reset():
    """세션 초기화"""
    session.clear()
    return jsonify({"status": "ok"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
