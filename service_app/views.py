import json
from django.shortcuts import render
from django.http import JsonResponse
import base64
from urllib.parse import quote
import uuid
from datetime import datetime
import requests
from .models import WorkSession, WorkSessionAction, PauseReason
from datetime import datetime, timedelta  # Добавляем импорт timedelta
BASE_URL = "http://192.168.1.3/sklad20/ru_RU/hs/ServiceAPI"
USERNAME = "ВнешнееСоединение"
PASSWORD = ""
AUTH_STR = f"{USERNAME}:{PASSWORD}"
AUTH_ENCODED = base64.b64encode(AUTH_STR.encode("utf-8")).decode("utf-8")
HEADERS = {"Authorization": f"Basic {AUTH_ENCODED}"}


def get_workers(request):
    url = f"{BASE_URL}/getworkers"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            workers = response.json()
        else:
            workers = []
    except requests.RequestException as e:
        workers = []
    pause_reasons = ["Перерыв", "Обед", "Ожидание запчастей"]
    return render(request, 'welcome.html', {'workerssarray': workers, 'pause': pause_reasons})


def get_orders(request):
    if request.method == 'POST':
        executor_name = request.POST.get('executor_name')
        url = f"{BASE_URL}/getcars?executor={executor_name}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                orders = response.json()
            else:
                orders = []
        except requests.RequestException as e:
            orders = []
        return JsonResponse({'orders': orders})
    return JsonResponse({'error': 'Invalid request'}, status=400)


def get_works(request):
    if request.method == 'POST':
        executor = request.POST.get('executor_name')
        order = request.POST.get('order')
        if not order or not executor:
            return JsonResponse({'error': 'Укажите сотрудника и номер заказа'}, status=400)
        url = f"{BASE_URL}/getuwork/{order}/{executor}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                works = response.json()
            else:
                works = []
        except requests.RequestException as e:
            works = []

        # Фильтруем работы, исключая те, что уже есть в активных сессиях
        active_sessions = WorkSession.objects.filter(executor=executor, is_active=True)
        active_work_codes = {session.work_code for session in active_sessions}
        works = [work for work in works if work['Code'] not in active_work_codes]

        # Если есть активная работа (не на паузе), показываем только её
        active_session = active_sessions.filter(current_start__isnull=False).first()
        if active_session:
            works = [{
                'Code': active_session.work_code,
                'Work': active_session.work_description or active_session.work_code,
                'ZE': 'N/A',
                'Sec': active_session.time_left,
                'WorkerCode': active_session.worker_code
            }]

        return JsonResponse({'works': works})
    return JsonResponse({'error': 'Invalid request'}, status=400)


def make_pause(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        ordernum = request.POST.get('ordernum', '')
        worknum = request.POST.get('worknum', '').strip()
        executor = request.POST.get('executor', '')
        worker_code = request.POST.get('worker_code', '')
        intervals = request.POST.get('intervals', '[]')
        current_start = request.POST.get('start', '')
        time_left = request.POST.get('time_left', '0')
        work_description = request.POST.get('work_description', '')
        reason_code = request.POST.get('reason_code', '')
        end = request.POST.get('end', '')

        print(
            f"Action: {action}, Order: {ordernum}, Work: {worknum}, Executor: {executor}, WorkerCode: {worker_code}, "
            f"Intervals: {intervals}, CurrentStart: {current_start}, TimeLeft: {time_left}, Description: {work_description}, "
            f"ReasonCode: {reason_code}, End: {end}"
        )

        if action not in ['start', 'pause', 'finish', 'check', 'check_all']:
            return JsonResponse({'error': 'Invalid action'}, status=400)

        if action in ['start', 'pause', 'finish'] and not all([ordernum, worknum, executor]):
            return JsonResponse({'error': 'Missing required parameters'}, status=400)

        if action == 'check':
            try:
                session = WorkSession.objects.filter(executor=executor, work_code=worknum, is_active=True).first()
                if session and session.current_start:
                    try:
                        start_time = datetime.strptime(session.current_start, '%d.%m.%Y %H:%M:%S')
                        now = datetime.now()
                        elapsed_seconds = int((now - start_time).total_seconds())
                        updated_time_left = session.initial_time_left - elapsed_seconds
                        session.time_left = max(updated_time_left, 0)
                        session.save()
                        print(f"Check: Updated time_left to {session.time_left}")
                    except ValueError as e:
                        print(f"Error parsing current_start '{session.current_start}': {str(e)}")
                        return JsonResponse({'error': f"Invalid current_start format: {str(e)}"}, status=500)

                result = {
                    'session': {
                        'session_id': session.session_id if session else None,
                        'order_number': session.order_number if session else None,
                        'work_code': session.work_code if session else None,
                        'worker_code': session.worker_code if session else None,
                        'intervals': session.intervals if session else '[]',
                        'current_start': session.current_start if session else None,
                        'time_left': session.time_left if session else 0,
                        'is_active': session.is_active if session else False,
                        'work_description': session.work_description if session else None,
                        'actions': [
                            {
                                'action': action.action,
                                'reason_code': action.reason_code,
                                'start': action.start,
                                'end': action.end,
                                'timestamp': action.timestamp.isoformat()
                            } for action in session.actions.all()
                        ] if session else []
                    } if session else None
                }
                print(f"Returning check result: {result}")
                return JsonResponse(result)
            except Exception as e:
                print(f"Error in check action: {str(e)}")
                return JsonResponse({'error': f"Server error: {str(e)}"}, status=500)

        elif action == 'check_all':
            try:
                sessions_list = WorkSession.objects.filter(executor=executor, is_active=True)
                for session in sessions_list:
                    if session.current_start:
                        try:
                            start_time = datetime.strptime(session.current_start, '%d.%m.%Y %H:%M:%S')
                            now = datetime.now()
                            elapsed_seconds = int((now - start_time).total_seconds())
                            updated_time_left = session.initial_time_left - elapsed_seconds
                            session.time_left = max(updated_time_left, 0)
                            session.save()
                            print(f"Check_all: Updated time_left for {session.work_code} to {session.time_left}")
                        except ValueError as e:
                            print(f"Error parsing current_start '{session.current_start}': {str(e)}")
                result = {
                    'sessions': [
                        {
                            'session_id': session.session_id,
                            'order_number': session.order_number,
                            'work_code': session.work_code,
                            'worker_code': session.worker_code,
                            'intervals': session.intervals,
                            'current_start': session.current_start,
                            'time_left': session.time_left,
                            'is_active': session.is_active,
                            'work_description': session.work_description,
                            'actions': [
                                {
                                    'action': action.action,
                                    'reason_code': action.reason_code,
                                    'start': action.start,
                                    'end': action.end,
                                    'timestamp': action.timestamp.isoformat()
                                } for action in session.actions.all()
                            ]
                        } for session in sessions_list
                    ]
                }
                print(f"Returning all sessions: {result}")
                return JsonResponse(result)
            except Exception as e:
                print(f"Error in check_all action: {str(e)}")
                return JsonResponse({'error': f"Server error: {str(e)}"}, status=500)

        else:
            try:
                session = WorkSession.objects.filter(executor=executor, work_code=worknum, is_active=True).first()

                if not session and action == 'start':
                    session = WorkSession(
                        session_id=str(uuid.uuid4()),
                        worker_code=worker_code or 'unknown',
                        order_number=ordernum,
                        work_code=worknum,
                        executor=executor,
                        intervals=intervals,
                        current_start=current_start or datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                        time_left=int(time_left) if time_left else 0,
                        initial_time_left=int(time_left) if time_left else 0,
                        is_active=True,
                        work_description=work_description
                    )
                    session.save()
                elif not session:
                    existing_sessions = WorkSession.objects.filter(executor=executor, is_active=True)
                    print(f"No session found for work {worknum}. Existing sessions: {[s.work_code for s in existing_sessions]}")
                    return JsonResponse({'error': f'Session not found for work {worknum}'}, status=404)

                try:
                    session_intervals = json.loads(intervals)
                except json.JSONDecodeError as e:
                    print(f"Invalid intervals JSON: {intervals}, error: {str(e)}")
                    session_intervals = []
                    session.set_intervals([])

                # Проверка на дублирование запросов
                if action in ['start', 'pause', 'finish']:
                    recent_action = WorkSessionAction.objects.filter(
                        session=session,
                        action=action,
                        timestamp__gte=datetime.now() - timedelta(seconds=2)
                    ).first()
                    if recent_action:
                        print(f"Duplicate action detected: {action} for {worknum}, skipping")
                        return JsonResponse({
                            'status': 'skipped',
                            'message': f'Duplicate {action} request detected'
                        })

                if action == 'start':
                    session.current_start = current_start or datetime.now().strftime('%d.%m.%Y %H:%M:%S')
                    session.time_left = int(time_left)
                    session.initial_time_left = int(time_left)
                    session.is_active = True
                elif action == 'pause':
                    if session.current_start:
                        try:
                            start_time = datetime.strptime(session.current_start, '%d.%m.%Y %H:%M:%S')
                            now = datetime.now()
                            elapsed_seconds = int((now - start_time).total_seconds())
                            session.time_left = max(session.initial_time_left - elapsed_seconds, int(time_left))
                            print(f"Pause: Updated time_left to {session.time_left}")
                        except ValueError as e:
                            print(f"Error parsing current_start '{session.current_start}': {str(e)}")
                            session.time_left = int(time_left)
                    session.current_start = None
                    session.is_active = True
                elif action == 'finish':
                    if session.current_start:
                        try:
                            start_time = datetime.strptime(session.current_start, '%d.%m.%Y %H:%M:%S')
                            now = datetime.now()
                            elapsed_seconds = int((now - start_time).total_seconds())
                            session.time_left = max(session.initial_time_left - elapsed_seconds, int(time_left))
                        except ValueError as e:
                            print(f"Error parsing current_start '{session.current_start}': {str(e)}")
                            session.time_left = int(time_left)
                    session.current_start = None
                    session.is_active = False

                if work_description and work_description.strip():
                    session.work_description = work_description
                session.worker_code = worker_code or session.worker_code
                session.save()

                WorkSessionAction.objects.create(
                    session=session,
                    action=action,
                    reason_code=reason_code if action == 'pause' else None,
                    start=current_start if action == 'start' else None,
                    end=end if action in ['pause', 'finish'] else None
                )

                # Формируем данные в новом формате
                data = {
                    "OrderNumber": ordernum,
                    "WorkerCode": worker_code,
                    "WorkCode": worknum,
                    "Action": action,
                    "Intervals": {}
                }
                now = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
                if action == "start":
                    data["Intervals"]["start"] = session.current_start or now
                elif action == "pause" and reason_code:
                    # Ищем последнее start из истории действий
                    last_start_action = WorkSessionAction.objects.filter(
                        session=session,
                        action='start'
                    ).order_by('-timestamp').first()
                    start_time = current_start
                    if not start_time and last_start_action and last_start_action.start:
                        start_time = last_start_action.start
                    elif not start_time and session.current_start:
                        start_time = session.current_start
                    elif not start_time and session_intervals:
                        start_time = session_intervals[-1].get('start', '') if session_intervals else ''
                    data["Intervals"]["start"] = start_time or now
                    data["Intervals"]["end"] = end or now
                    data["Intervals"]["reasonCode"] = reason_code
                elif action == "finish":
                    last_start_action = WorkSessionAction.objects.filter(
                        session=session,
                        action='start'
                    ).order_by('-timestamp').first()
                    start_time = current_start
                    if not start_time and last_start_action and last_start_action.start:
                        start_time = last_start_action.start
                    elif not start_time and session.current_start:
                        start_time = session.current_start
                    elif not start_time and session_intervals:
                        start_time = session_intervals[-1].get('start', '') if session_intervals else ''
                    data["Intervals"]["start"] = start_time or now
                    data["Intervals"]["end"] = end or now

                try:
                    # Логируем данные в файл для отладки
                    with open('1c_requests.txt', 'a', encoding='utf-8') as f:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        f.write(f"[{timestamp}] POST to {BASE_URL}/makeWorkRecord\n")
                        f.write(f"Data: {json.dumps(data, ensure_ascii=False, indent=2)}\n")
                        f.write("---\n")

                    # Отправляем данные на новый endpoint
                    url = f"{BASE_URL}/makeWorkRecord"
                    response = requests.post(url, json=data, headers=HEADERS, timeout=5)
                    if response.status_code == 200:
                        result = {
                            'status': 'success',
                            'message': 'Request successfully sent to 1C',
                            'response': response.json()
                        }
                    else:
                        print(f"Failed to send request to 1C: {response.status_code} {response.text}")
                        with open('1c_requests.txt', 'a', encoding='utf-8') as f:
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            f.write(f"[{timestamp}] POST to {url}\n")
                            f.write(f"Data: {json.dumps(data, ensure_ascii=False, indent=2)}\n")
                            f.write(f"Error: {response.status_code} {response.text}\n")
                            f.write("---\n")
                        result = {
                            'status': 'logged',
                            'message': f'Request logged to 1c_requests.txt due to error: {response.status_code}'
                        }
                except requests.RequestException as e:
                    print(f"Error sending request to 1C: {str(e)}")
                    with open('1c_requests.txt', 'a', encoding='utf-8') as f:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        f.write(f"[{timestamp}] POST to {url}\n")
                        f.write(f"Data: {json.dumps(data, ensure_ascii=False, indent=2)}\n")
                        f.write(f"Error: {str(e)}\n")
                        f.write("---\n")
                    result = {
                        'status': 'logged',
                        'message': f'Request logged to 1c_requests.txt due to error: {str(e)}'
                    }

                return JsonResponse(result)
            except Exception as e:
                print(f"Error in action {action}: {str(e)}")
                return JsonResponse({'error': f"Server error: {str(e)}"}, status=500)

    return JsonResponse({'error': 'Invalid request'}, status=400)


def get_cars(request, executor):
    url = f"{BASE_URL}/getcars?executor={executor}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            cars = response.json()
        else:
            cars = []
    except requests.RequestException as e:
        cars = []
    return JsonResponse(cars)
def get_pause_reasons(request):
    if request.method == 'GET':
        try:
            reasons = PauseReason.objects.all()
            reasons_list = [{'code': reason.code, 'description': reason.description} for reason in reasons]
            return JsonResponse({'pause_reasons': reasons_list})
        except Exception as e:
            print(f"Error fetching pause reasons: {str(e)}")
            return JsonResponse({'error': f"Server error: {str(e)}"}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)