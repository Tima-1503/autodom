import json
from django.shortcuts import render
from django.http import JsonResponse
import base64
from urllib.parse import quote
import uuid
from datetime import datetime
import requests
from .models import WorkSession

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

        active_session = WorkSession.objects.filter(executor=executor, is_active=True).first()
        if active_session:
            works = [{
                'Code': active_session.work_code,
                'Work': active_session.work_description or active_session.work_code,  # Используем сохранённое описание
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
        worknum = request.POST.get('worknum', '')
        executor = request.POST.get('executor', '')
        worker_code = request.POST.get('worker_code', '')
        intervals = request.POST.get('intervals', '[]')
        current_start = request.POST.get('current_start', '')
        time_left = request.POST.get('time_left', '0')
        work_description = request.POST.get('work_description', '')  # Новое поле для описания

        print(
            f"Action: {action}, Order: {ordernum}, Work: {worknum}, Executor: {executor}, WorkerCode: {worker_code}, Intervals: {intervals}, CurrentStart: {current_start}, TimeLeft: {time_left}, Description: {work_description}")

        if action in ['start', 'resume', 'pause', 'finish', 'update'] and not all(
                [ordernum, worknum, executor, worker_code]):
            return JsonResponse({'error': 'Missing required parameters'}, status=400)

        if action == 'check':
            session = WorkSession.objects.filter(executor=executor, work_code=worknum,
                                                 is_active=True).first() if worknum else WorkSession.objects.filter(
                executor=executor, is_active=True).first()
            result = {
                'session': {
                    'session_id': session.session_id,
                    'order_number': session.order_number,
                    'work_code': session.work_code,
                    'worker_code': session.worker_code,
                    'intervals': session.intervals,
                    'current_start': session.current_start,
                    'time_left': session.time_left,
                    'is_active': session.is_active,
                    'work_description': session.work_description
                } if session else None
            }
        else:
            session, created = WorkSession.objects.get_or_create(
                worker_code=worker_code,
                work_code=worknum,
                is_active=True,
                defaults={
                    'session_id': str(uuid.uuid4()),
                    'worker_code': worker_code,
                    'order_number': ordernum,
                    'work_code': worknum,
                    'executor': executor,
                    'intervals': intervals,
                    'current_start': current_start if current_start else None,
                    'time_left': int(time_left) if time_left else 0,
                    'is_active': True,
                    'work_description': work_description  # Сохраняем описание
                }
            )

            if not created:
                try:
                    session.set_intervals(json.loads(intervals))
                except json.JSONDecodeError as e:
                    print(f"Invalid intervals JSON: {intervals}, error: {str(e)}")
                    session.set_intervals([])
                session.current_start = current_start if current_start else None
                session.time_left = int(time_left) if time_left else 0
                session.is_active = action != 'finish'
                if work_description:
                    session.work_description = work_description
                session.save()

            if action == "finish":
                data = {
                    "SessionID": session.session_id,
                    "WorkerCode": worker_code,
                    "OrderNumber": ordernum,
                    "WorkCode": worknum,
                    "Action": action,
                    "Intervals": json.loads(intervals) if intervals else []
                }
                try:
                    with open('1c_requests.txt', 'a', encoding='utf-8') as f:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        f.write(f"[{timestamp}] POST to {BASE_URL}/mpause\n")
                        f.write(f"Data: {json.dumps(data, ensure_ascii=False, indent=2)}\n")
                        f.write("---\n")
                    result = {
                        'status': 'logged',
                        'message': 'Request logged to 1c_requests.txt (1C server not available)'
                    }
                except Exception as e:
                    print(f"Error writing to file: {str(e)}")
                    result = {'error': f'Failed to log request: {str(e)}'}
            else:
                result = {'status': 'saved', 'message': 'Session updated in database'}

        return JsonResponse(result, safe=False)
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