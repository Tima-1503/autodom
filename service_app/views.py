import json
from django.shortcuts import render
from django.http import JsonResponse
import base64
from urllib.parse import quote
import uuid
from datetime import datetime, timedelta
import requests
from .models import WorkSession, WorkSessionAction, PauseReason

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
            print(f"Workers fetched: {len(workers)}")
            workers = sorted(workers, key=lambda x: x.get('Worker', '').lower())
        else:
            workers = []
            print(f"Failed to fetch workers: {response.status_code}")
    except requests.RequestException as e:
        workers = []
        print(f"Error fetching workers: {str(e)}")
    pause_reasons = ["Перерыв", "Обед", "Ожидание запчастей"]
    return render(request, 'welcome.html', {'workerssarray': workers, 'pause': pause_reasons})

def get_orders(request):
    if request.method == 'POST':
        executor_name = request.POST.get('executor_name')
        if not executor_name:
            print("No executor_name provided")
            return JsonResponse({'error': 'Executor name required'}, status=400)
        url = f"{BASE_URL}/getcars?executor={quote(executor_name)}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                orders = response.json()
                print(f"Orders fetched for {executor_name}: {len(orders)} orders")
                # Убедимся, что каждое поле заказа включает Finished
                for order in orders:
                    order['Finished'] = order.get('Finished', False)
            else:
                orders = []
                print(f"Failed to fetch orders: {response.status_code}")
        except requests.RequestException as e:
            orders = []
            print(f"Error fetching orders: {str(e)}")
        return JsonResponse({'orders': orders})
    print("Invalid request method for get_orders")
    return JsonResponse({'error': 'Invalid request'}, status=400)

def get_works(request):
    if request.method == 'POST':
        executor = request.POST.get('executor_name')
        order = request.POST.get('order')
        if not order or not executor:
            print(f"Missing parameters: executor={executor}, order={order}")
            return JsonResponse({'error': 'Укажите сотрудника и номер заказа'}, status=400)
        url = f"{BASE_URL}/getuwork/{quote(order)}/{quote(executor)}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                works = response.json()
                print(f"Works fetched for order={order}, executor={executor}: {len(works)}")
            else:
                works = []
                print(f"Failed to fetch works: {response.status_code}")
        except requests.RequestException as e:
            works = []
            print(f"Error fetching works: {str(e)}")

        # Получаем все активные и завершённые сессии для данного заказа
        active_sessions = WorkSession.objects.filter(order_number=order)
        active_work_codes = {session.work_code.strip() for session in active_sessions}

        # Получаем паузы для текущего сотрудника
        paused_sessions = active_sessions.filter(
            executor=executor,
            current_start__isnull=True,
            is_active=True,
            is_finished=False
        )
        paused_work_codes = {session.work_code.strip() for session in paused_sessions}

        # Очищаем пробелы в кодах работ из 1C и фильтруем
        filtered_works = []
        for work in works:
            work_code = work.get('Code', '').strip()
            if work_code and work_code not in active_work_codes and work_code not in paused_work_codes:
                work['Code'] = work_code
                filtered_works.append(work)
        works = filtered_works

        # Проверяем активные сессии для текущего сотрудника
        executor_sessions = active_sessions.filter(executor=executor, is_active=True, is_finished=False)

        # Проверяем, есть ли активная работа (не на паузе) для сотрудника
        active_session = executor_sessions.filter(current_start__isnull=False).first()
        if active_session:
            # Возвращаем только активную работу
            works = [{
                'Code': active_session.work_code.strip(),
                'Work': active_session.work_description or active_session.work_code,
                'ZE': 'N/A',
                'Sec': active_session.time_left,
                'WorkerCode': active_session.worker_code
            }]
            print(f"Returning active work: {active_session.work_code}")

        print(f"Works returned for executor={executor}, order={order}: {len(works)}")
        return JsonResponse({'works': works})
    print("Invalid request method for get_works")
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
            print(f"Invalid action: {action}")
            return JsonResponse({'error': 'Invalid action'}, status=400)

        if action in ['start', 'pause', 'finish'] and not all([ordernum, worknum, executor]):
            print("Missing required parameters")
            return JsonResponse({'error': 'Missing required parameters'}, status=400)

        if action == 'check':
            try:
                session = WorkSession.objects.filter(executor=executor, work_code=worknum, is_active=True, is_finished=False).first()
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
                        'is_finished': session.is_finished if session else False,
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
                # Получаем все сессии для исполнителя
                sessions_list = WorkSession.objects.filter(executor=executor).order_by('-id')
                # Фильтруем дубликаты, оставляя последнюю сессию для каждой комбинации
                unique_sessions = {}
                for session in sessions_list:
                    key = (session.executor, session.order_number, session.work_code)
                    if key not in unique_sessions:
                        unique_sessions[key] = session
                    else:
                        # Пропускаем старую сессию
                        continue

                sessions_list = list(unique_sessions.values())
                for session in sessions_list:
                    if session.current_start and session.is_active and not session.is_finished:
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
                            'is_finished': session.is_finished,
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
                print(f"Returning all sessions: {len(result['sessions'])}")
                return JsonResponse(result)
            except Exception as e:
                print(f"Error in check_all action: {str(e)}")
                return JsonResponse({'error': f"Server error: {str(e)}"}, status=500)

        else:
            try:
                # Проверяем, не взята ли работа другим сотрудником
                if action == 'start':
                    existing_session = WorkSession.objects.filter(
                        order_number=ordernum,
                        work_code=worknum,
                        is_active=True,
                        is_finished=False
                    ).exclude(executor=executor).first()
                    if existing_session:
                        print(f"Work {worknum} already taken by {existing_session.executor}")
                        return JsonResponse({
                            'error': f'Работа {worknum} уже взята сотрудником {existing_session.executor}'
                        }, status=400)

                # Проверяем существующую сессию
                session = WorkSession.objects.filter(
                    executor=executor,
                    order_number=ordernum,
                    work_code=worknum
                ).order_by('-id').first()

                if action == 'start':
                    if session and session.is_finished:
                        print(f"Previous session {session.session_id} is finished, creating new session")
                        session = None  # Создаём новую сессию, если старая завершена
                    if session and session.current_start:
                        # Сессия уже активна, обновляем
                        print(f"Session {session.session_id} already active, updating")
                        session.current_start = current_start or datetime.now().strftime('%d.%m.%Y %H:%M:%S')
                        session.time_left = int(time_left) if time_left else session.time_left
                        session.initial_time_left = int(time_left) if time_left else session.initial_time_left
                        session.is_active = True
                        session.is_finished = False
                        session.intervals = '[]'  # Очищаем интервалы при старте
                        session.save()
                    else:
                        # Закрываем старую сессию (если есть, например, на паузе)
                        if session:
                            print(f"Closing paused session: {session.session_id}")
                            session.is_active = False
                            session.is_finished = False
                            session.save()

                        # Закрываем все старые сессии для этой комбинации
                        old_sessions = WorkSession.objects.filter(
                            executor=executor,
                            order_number=ordernum,
                            work_code=worknum
                        ).exclude(session_id=session.session_id if session else None)
                        for old_session in old_sessions:
                            print(f"Closing old session: {old_session.session_id}")
                            old_session.is_active = False
                            old_session.is_finished = False
                            old_session.save()

                        # Создаём новую сессию
                        session = WorkSession(
                            session_id=str(uuid.uuid4()),
                            worker_code=worker_code or 'unknown',
                            order_number=ordernum,
                            work_code=worknum,
                            executor=executor,
                            intervals='[]',
                            current_start=current_start or datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                            time_left=int(time_left) if time_left else 0,
                            initial_time_left=int(time_left) if time_left else 0,
                            is_active=True,
                            is_finished=False,
                            work_description=work_description
                        )
                        session.save()
                        print(f"Created new session: {session.session_id}")

                elif action == 'pause':
                    if not session:
                        print(f"No active session found for work {worknum}")
                        return JsonResponse({'error': f'No active session for work {worknum}'}, status=404)
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
                    # Сохраняем только текущий интервал
                    session_intervals = [{
                        'start': session.current_start,
                        'end': end or datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                        'reasonCode': reason_code
                    }]
                    session.set_intervals(session_intervals)
                    session.current_start = None
                    session.is_active = True
                    session.is_finished = False
                    session.save()

                elif action == 'finish':
                    if not session:
                        print(f"No active session found for work {worknum}")
                        return JsonResponse({'error': f'No active session for work {worknum}'}, status=404)
                    if session.current_start:
                        try:
                            start_time = datetime.strptime(session.current_start, '%d.%m.%Y %H:%M:%S')
                            now = datetime.now()
                            elapsed_seconds = int((now - start_time).total_seconds())
                            session.time_left = max(session.initial_time_left - elapsed_seconds, int(time_left))
                        except ValueError as e:
                            print(f"Error parsing current_start '{session.current_start}': {str(e)}")
                            session.time_left = int(time_left)
                    # Сохраняем только финальный интервал
                    session_intervals = [{
                        'start': session.current_start or current_start,
                        'end': end or datetime.now().strftime('%d.%m.%Y %H:%M:%S')
                    }]
                    session.set_intervals(session_intervals)
                    session.current_start = None
                    session.is_active = False
                    session.is_finished = True
                    session.save()
                    print(f"Finished session: {session.session_id}")

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

                # Формируем данные для 1C
                data = {
                    "OrderNumber": ordernum,
                    "WorkerCode": worker_code,
                    "WorkCode": worknum,
                    "Action": action,
                    "Intervals": {}
                }
                now = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
                start_time = None
                if action == "start":
                    start_time = session.current_start or current_start or now
                elif action in ["pause", "finish"]:
                    if session.current_start:
                        start_time = session.current_start
                    else:
                        try:
                            session_intervals = json.loads(session.intervals) if session.intervals else []
                            if session_intervals:
                                start_time = session_intervals[-1].get('start', '')
                        except json.JSONDecodeError:
                            print(f"Invalid intervals JSON in DB: {session.intervals}")
                    if not start_time:
                        last_start_action = WorkSessionAction.objects.filter(
                            session=session,
                            action='start'
                        ).order_by('-timestamp').first()
                        if last_start_action and last_start_action.start:
                            start_time = last_start_action.start
                    if not start_time:
                        start_time = current_start or now

                if action == "start":
                    data["Intervals"]["start"] = start_time
                elif action == "pause" and reason_code:
                    data["Intervals"]["start"] = start_time
                    data["Intervals"]["end"] = end or now
                    data["Intervals"]["reasonCode"] = reason_code
                elif action == "finish":
                    data["Intervals"]["start"] = start_time
                    data["Intervals"]["end"] = end or now

                # Отправляем запрос в 1C
                try:
                    url = f"{BASE_URL}/makeWorkRecord"
                    with open('1c_requests.txt', 'a', encoding='utf-8') as f:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        f.write(f"[{timestamp}] POST to {url}\n")
                        f.write(f"Data: {json.dumps(data, ensure_ascii=False, indent=2)}\n")
                        f.write("---\n")

                    response = requests.post(url, json=data, headers=HEADERS, timeout=5)
                    if response.status_code in [200, 204]:
                        result = {
                            'status': 'success',
                            'message': 'Request successfully sent to 1C',
                            'response': response.text or 'No content'
                        }
                        print(f"1C response: status={response.status_code}, body={response.text}")
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

    print("Invalid request method for make_pause")
    return JsonResponse({'error': 'Invalid request'}, status=400)

def get_cars(request, executor):
    url = f"{BASE_URL}/getcars?executor={quote(executor)}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        if response.status_code == 200:
            cars = response.json()
            print(f"Cars fetched for {executor}: {len(cars)}")
            # Убедимся, что каждое поле заказа включает Finished
            for car in cars:
                car['Finished'] = car.get('Finished', False)
        else:
            cars = []
            print(f"Failed to fetch cars: {response.status_code}")
    except requests.RequestException as e:
        cars = []
        print(f"Error fetching cars: {str(e)}")
    return JsonResponse({'cars': cars})

def get_pause_reasons(request):
    if request.method == 'GET':
        try:
            reasons = PauseReason.objects.all()
            reasons_list = [{'code': reason.code, 'description': reason.description} for reason in reasons]
            print(f"Pause reasons fetched: {len(reasons_list)}")
            return JsonResponse({'pause_reasons': reasons_list})
        except Exception as e:
            print(f"Error fetching pause reasons: {str(e)}")
            return JsonResponse({'error': f"Server error: {str(e)}"}, status=500)
    print("Invalid request method for get_pause_reasons")
    return JsonResponse({'error': 'Invalid request'}, status=400)