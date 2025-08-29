from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.conf import settings
import json
import bcrypt
import logging
from datetime import datetime, date
from .models import User, Task
from .cache import get_cached_tasks, set_cached_tasks, clear_cached_tasks, task_cache
import os

logger = logging.getLogger(__name__)

TELEMETRY_LOG = []
TELEMETRY_MAX = 100


def log_telemetry(event, username=None, details=None):
    entry = {
        "event": event,
        "username": username,
        "details": details,
        "timestamp": datetime.now().isoformat(),
    }
    TELEMETRY_LOG.append(entry)
    if len(TELEMETRY_LOG) > TELEMETRY_MAX:
        TELEMETRY_LOG.pop(0)
    logger.info(f"TELEMETRY: {entry}")


def login_page(request):
    return render(request, "login.html")


def signup_page(request):
    return render(request, "signup.html")


def home(request):
    if "username" not in request.session:
        return redirect("login_page")
    logger.info(f"User {request.session['username']} accessing home page.")
    return render(request, "home.html")


def index(request):
    if "username" in request.session:
        logger.info(
            f"User {request.session['username']} is already logged in, redirecting to home."
        )
        return redirect("home")
    logger.info("No user logged in, redirecting to login page.")
    return redirect("login_page")


def custom_login_required(view_func):
    def wrapper(request, *args, **kwargs):
        if "username" not in request.session:
            if request.path.startswith("/api/"):
                return JsonResponse(
                    {"success": False, "error": "Not logged in"}, status=401
                )
            return redirect("login_page")
        return view_func(request, *args, **kwargs)

    return wrapper


@csrf_exempt
@require_http_methods(["GET"])
def get_user(request):
    username = request.session.get("username")
    if username:
        return JsonResponse({"success": True, "username": username})
    return JsonResponse({"success": False, "error": "User not logged in"}, status=401)


@csrf_exempt
@require_http_methods(["POST"])
def api_signup(request):
    logger.info("Received signup request.")

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return JsonResponse(
            {"success": False, "error": "Username and password are required."},
            status=400,
        )
    if User.objects.filter(username=username).exists():
        logger.warning(f"Signup failed: Username {username} already exists.")
        return JsonResponse(
            {"success": False, "error": "Username already exists."}, status=409
        )

    try:
        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        User.objects.create(username=username, password=hashed_pw.decode("utf-8"))

        logger.info(f"User {username} signed up successfully.")
        return JsonResponse(
            {"success": True, "message": "Signup successful. Please log in."},
            status=201,
        )

    except Exception as e:
        logger.error(f"Database error in signup: {e}")
        return JsonResponse(
            {"success": False, "error": "Internal server error."}, status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return JsonResponse(
            {"success": False, "error": "Username and password are required."},
            status=400,
        )

    try:
        user = User.objects.filter(username=username).first()

        if user and bcrypt.checkpw(
            password.encode("utf-8"), user.password.encode("utf-8")
        ):
            request.session["username"] = username
            logger.info(f"User {username} logged in successfully.")
            return JsonResponse(
                {
                    "success": True,
                    "message": "Login successful.",
                    "redirect_url": "/home",
                },
                status=200,
            )
        else:
            logger.warning(f"Failed login attempt for username: {username}")
            return JsonResponse(
                {"success": False, "error": "Invalid username or password."}, status=401
            )

    except Exception as e:
        logger.error(f"Database error in login: {e}")
        return JsonResponse(
            {"success": False, "error": "Internal server error."}, status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
@custom_login_required
def api_logout(request):
    request.session.pop("username", None)
    return JsonResponse({"success": True, "message": "Logged out."})


@csrf_exempt
@require_http_methods(["GET"])
@custom_login_required
def api_tasks(request):
    username = request.session["username"]

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        logger.warning(f"User {username} not found in database.")
        return JsonResponse({"success": False, "error": "User not found"}, status=404)

    page = int(request.GET.get("page", 1))
    limit = int(request.GET.get("limit", 10))

    cached_data = get_cached_tasks(username, page, limit)
    if cached_data is not None:
        return JsonResponse(
            {
                "success": True,
                "tasks": cached_data["tasks"],
                "page": page,
                "limit": limit,
                "total_count": cached_data["total_count"],
                "pages": (cached_data["total_count"] + limit - 1) // limit,
                "cache_hit": True,
            },
            status=200,
        )

    try:
        tasks = Task.objects.filter(user=user).order_by("-due_date")
        total_count = tasks.count()

        paginator = Paginator(tasks, limit)
        page_obj = paginator.get_page(page)

        result = [task.serialize() for task in page_obj.object_list]

        set_cached_tasks(username, result, total_count, page, limit)

        logger.info(f"Fetched {len(result)} tasks for user: {username}")
        return JsonResponse(
            {
                "success": True,
                "tasks": result,
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "pages": paginator.num_pages,
                "cache_hit": False,
            },
            status=200,
        )

    except Exception as e:
        logger.error(f"Database error in /api/tasks: {e}")
        return JsonResponse({"success": False, "error": "Database error"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@custom_login_required
def add_task(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    title = data.get("Title") or data.get("title")
    description = data.get("Description") or data.get("description")
    due_date = data.get("due_date") or data.get("dueDate")

    if not title or not due_date:
        return JsonResponse(
            {"success": False, "error": "Title and due date required."}, status=400
        )

    try:
        user = User.objects.get(username=request.session["username"])

        # Create task
        Task.objects.create(
            user=user,
            Title=title,
            Description=description or "",
            due_date=due_date,
            is_completed=False,
        )

        clear_cached_tasks(request.session["username"])

        log_telemetry(
            "add_task",
            username=user.username,
            details={"title": title, "due_date": due_date},
        )

        return JsonResponse(
            {"success": True, "message": "Task Created Successfully"}, status=201
        )

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found."}, status=404)
    except Exception as e:
        logger.error(f"Database error in add_task: {e}")
        return JsonResponse({"success": False, "error": "Database error"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@custom_login_required
def edit_task(request, task_id):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    new_title = data.get("title")
    new_description = data.get("description")
    due_date = data.get("due_date")

    logger.info(
        f"Edit task {task_id} - Received data: title={new_title}, description={new_description}, due_date={due_date}"
    )

    if not new_title or not due_date:
        return JsonResponse(
            {"success": False, "error": "Title and due date required."}, status=400
        )

    try:
        user = User.objects.get(username=request.session["username"])
        task = get_object_or_404(Task, id=task_id, user=user)

        task.Title = new_title
        task.Description = new_description or ""
        task.due_date = due_date
        task.save()
        clear_cached_tasks(request.session["username"])

        log_telemetry(
            "edit_task",
            username=user.username,
            details={"task_id": task_id, "new_title": new_title, "due_date": due_date},
        )

        return JsonResponse({"success": True, "task": task.serialize()})

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found."}, status=404)
    except Exception as e:
        logger.error(f"Database error in edit_task: {e}")
        return JsonResponse({"success": False, "error": "Database error"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@custom_login_required
def delete_task(request, task_id):
    try:
        user = User.objects.get(username=request.session["username"])
        task = get_object_or_404(Task, id=task_id, user=user)

        task.delete()

        # Clear cache
        clear_cached_tasks(request.session["username"])

        log_telemetry(
            "delete_task", username=user.username, details={"task_id": task_id}
        )

        logger.info(
            f"Task {task_id} deleted successfully for user {request.session['username']}"
        )
        return JsonResponse({"success": True})

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found."}, status=404)
    except Exception as e:
        logger.error(f"Database error in delete_task: {e}")
        return JsonResponse({"success": False, "error": "Database error"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@custom_login_required
def toggle_complete(request, task_id):
    try:
        user = User.objects.get(username=request.session["username"])
        task = get_object_or_404(Task, id=task_id, user=user)

        # Toggle completion status
        task.is_completed = not task.is_completed
        task.save()

        # Clear cache
        clear_cached_tasks(request.session["username"])

        log_telemetry(
            "toggle_complete",
            username=user.username,
            details={"task_id": task_id, "is_completed": task.is_completed},
        )

        return JsonResponse({"success": True, "is_completed": task.is_completed})

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found."}, status=404)
    except Exception as e:
        logger.error(f"Database error in toggle_complete: {e}")
        return JsonResponse({"success": False, "error": "Database error"}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def cache_stats(request):
    stats = task_cache.get_stats()
    return JsonResponse({"success": True, "cache_stats": stats})


@csrf_exempt
@require_http_methods(["GET"])
def telemetry(request):
    return JsonResponse({"success": True, "telemetry": TELEMETRY_LOG[-TELEMETRY_MAX:]})
