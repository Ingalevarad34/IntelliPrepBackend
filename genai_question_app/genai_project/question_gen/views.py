from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.conf import settings
from django.db import models
import razorpay
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import google.generativeai as genai
import re
import PyPDF2
from io import BytesIO
from .models import ContactMessage
import urllib.parse
import base64
from datetime import datetime

# Import models
from .models import User, InterviewRequest, ChatMessage

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)
client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
# Current stable model (December 2025)
GEMINI_MODEL = 'gemini-2.5-flash-lite'

# ==================== AUTH VIEWS ====================
def register(request):
    if request.method == 'POST':
        username = request.POST['username']
        email = request.POST['email']
        password1 = request.POST['password1']
        password2 = request.POST['password2']
        user_type = request.POST['user_type']

        if password1 != password2:
            messages.error(request, "Passwords do not match")
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken")
            return redirect('register')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            user_type=user_type
        )

        if user_type == 'interviewer':
            user.package = request.POST.get('package', '')
            user.company = request.POST.get('company', '')
            user.role = request.POST.get('role', '')
            user.skills = request.POST.get('skills', '')
            user.bio = request.POST.get('bio', '')
            user.profile_image = request.POST.get('profile_image', '')

        user.save()
        login(request, user)
        messages.success(request, f"Welcome {username}! Account created.")
        return redirect('landing')

    return render(request, 'registration/register.html')

def user_login(request):
    next_page = request.GET.get('next')

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            redirect_to = request.POST.get('next') or request.GET.get('next') or 'landing'
            return redirect(redirect_to)
        messages.error(request, "Invalid credentials")

    return render(request, 'registration/login.html', {'next': next_page})

@login_required
def user_logout(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect('landing')

# ==================== MAIN VIEWS ====================
@login_required
def landing(request):
    user = request.user

    # Admin → redirect to admin panel
    if user.user_type == 'admin':
        return redirect('admin:index')

    # Interviewer / Mentor Dashboard
    if user.user_type == 'interviewer':
        # Pending requests
        pending_requests = InterviewRequest.objects.filter(
            interviewer=user, 
            status='pending'
        ).order_by('requested_date')

        # All requests (for calendar drawer)
        all_requests = InterviewRequest.objects.filter(
            interviewer=user
        ).order_by('-requested_date')

        # Active chats: students who have messaged this interviewer
        active_students = User.objects.filter(
            sent_messages__receiver=user
        ).annotate(
            last_message_time=models.Max('sent_messages__timestamp')
        ).order_by('-last_message_time')

        return render(request, 'question_gen/mentor_dashboard.html', {
            'pending_requests': pending_requests,
            'all_requests': all_requests,        # For calendar drawer
            'active_chats': active_students,     # With last message time
        })

    # Student Landing Page (default)
    mentors = User.objects.filter(user_type='interviewer').order_by('-date_joined')[:6]
    
    return render(request, 'question_gen/landing.html', {
        'mentors': mentors
    })
@login_required
def select_topic(request):
    if request.method == 'POST':
        topic = request.POST.get('topic', '').strip()
        document_file = request.FILES.get('document')
        summary = ''

        if document_file:
            try:
                pdf_reader = PyPDF2.PdfReader(BytesIO(document_file.read()))
                text = ''
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    text += (page_text or '') + '\n'

                model = genai.GenerativeModel(GEMINI_MODEL)
                sum_prompt = f"Summarize key points clearly (focus on {topic} if relevant): {text[:4000]}"
                summary = model.generate_content(sum_prompt).text.strip()
                messages.success(request, "Document summarized!")
            except Exception as e:
                messages.error(request, f"PDF error: {str(e)}")
                return render(request, 'question_gen/select_topic.html')

        if not document_file and topic not in ['java', 'javascript', 'reactjs']:
            messages.error(request, "Select valid topic or upload PDF.")
            return render(request, 'question_gen/select_topic.html')

        try:
            model = genai.GenerativeModel(GEMINI_MODEL)
            base_context = f"Document summary: {summary}. " if summary else ''
            prompt = (
                f"You are a friendly quiz master. "
                f"Topic: {topic or 'Custom Document'}. {base_context}"
                "Create engaging beginner question. Start with warm compliment, then question. Keep concise."
            )
            response = model.generate_content(prompt)
            full_text = response.text.strip()

            compliment, question = parse_response(full_text)

            request.session['history'] = []
            request.session['step'] = 1
            request.session['nest_level'] = 0
            request.session['topic'] = topic or 'Custom Document'
            request.session['document_summary'] = summary
            request.session['current_compliment'] = compliment
            request.session['current_question'] = question
            request.session.modified = True

            url_topic = (topic or 'custom-document').lower().replace(' ', '-')
            return redirect('quiz_view', topic=url_topic)

        except Exception as e:
            messages.error(request, f"Quiz generation error: {str(e)}")
            return render(request, 'question_gen/select_topic.html')

    return render(request, 'question_gen/select_topic.html')

def parse_response(full_text):
    # Your existing parse_response function (keep as is)
    full_lower = full_text.lower()
    if 'now,' in full_lower:
        split_idx = full_lower.find('now,')
        compliment = full_text[:split_idx].strip()
        question = full_text[split_idx:].strip()
    elif re.search(r'\.(?=\s*[A-Z])', full_text):
        split_match = re.search(r'\.(?=\s*[A-Z])', full_text)
        if split_match:
            split_idx = split_match.end()
            compliment = full_text[:split_idx].strip()
            question = full_text[split_idx:].strip()
        else:
            compliment = full_text.split('.')[0].strip() + '.' if '.' in full_text else ''
            question = full_text
    elif '?' in full_text:
        split_idx = full_text.find('?') + 1
        compliment = full_text[:split_idx].strip()
        question = full_text[split_idx:].strip()
    else:
        compliment = ''
        question = full_text

    question = re.sub(r'`history:`', 'Based on our discussion:', question)
    return compliment, question



@login_required
def quiz_view(request, topic):
    # Session validation
    if topic.replace('-', ' ').lower() != request.session.get('topic', '').lower():
        messages.error(request, 'Session expired. Please start a new quiz.')
        return redirect('landing')

    history = request.session.get('history', [])
    step = request.session.get('step', 1)
    nest_level = request.session.get('nest_level', 0)
    max_steps = 10
    summary = request.session.get('document_summary', '')

    # Quiz complete
    if step > max_steps:
        final_score = len([h for h in history if 'correct' in h.get('feedback', '').lower()])
        percentage = round((final_score / max_steps) * 100, 1)
        request.session.clear()
        return render(request, 'question_gen/quiz_end.html', {
            'history': history,
            'topic': topic.replace('-', ' ').title(),
            'total_steps': max_steps,
            'score': final_score,
            'percentage': percentage,
            'document_summary': summary
        })

    current_compliment = request.session.get('current_compliment', 'Welcome to your quiz!')
    current_question = request.session.get('current_question', 'Let\'s begin!')

    if request.method == 'POST':
        user_answer = request.POST.get('answer', '').strip()
        if not user_answer:
            messages.error(request, "Please provide an answer.")
            return redirect('quiz_view', topic=topic)

        try:
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            base_context = f"Document summary: {summary}. " if summary else ''
            context = base_context + '\n'.join([f"Q: {h['question']} A: {h['user_answer']}" for h in history[-3:]])

            # Judge answer
            judge_prompt = (
                f"Topic: {topic}. {context} "
                f"Current Question: {current_question} "
                f"User Answer: {user_answer} "
                "Is this correct? Answer with 'Correct!' or 'Incorrect: [short explanation]' only."
            )
            feedback = model.generate_content(judge_prompt).text.strip()

            # Extract concept
            concept_prompt = f"{base_context}From the answer '{user_answer}', extract ONE key technical concept/keyword to explore next."
            concept = model.generate_content(concept_prompt).text.strip()

            # Decide next level
            if nest_level < 2:
                nest_text = f"Nest deeper into '{concept}'"
                next_level = nest_level + 1
            else:
                nest_text = f"Branch to a new topic: '{concept}'"
                next_level = 0

            # Generate next question
            next_prompt = (
                f"You are a quiz master on {topic}. {base_context}{nest_text}. "
                f"Previous answer feedback: {feedback}. "
                f"Create a follow-up question on '{concept}'. "
                f"Start with a short compliment, then ask the question. Keep concise."
            )
            next_response = model.generate_content(next_prompt).text.strip()
            compliment, question = parse_response(next_response)

            # Save to history
            history.append({
                'question': current_question,
                'user_answer': user_answer,
                'concept': concept,
                'feedback': feedback,
                'nest_level': nest_level,
                'compliment': compliment
            })

            # Update session
            request.session['history'] = history
            request.session['step'] = step + 1
            request.session['nest_level'] = next_level
            request.session['current_compliment'] = compliment
            request.session['current_question'] = question
            request.session.modified = True

            if 'correct' in feedback.lower():
                messages.success(request, f"{feedback} → Exploring '{concept}' next!")
            else:
                messages.error(request, f"{feedback} → Let's explore '{concept}' anyway!")

            return redirect('quiz_view', topic=topic)

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect('quiz_view', topic=topic)

    topic_display = topic.replace('-', ' ').title()
    return render(request, 'question_gen/quiz_question.html', {
        'compliment': current_compliment,
        'question': current_question,
        'step': step,
        'total': max_steps,
        'nest_level': nest_level,
        'history': history[-3:],  # Show only last 3
        'topic': topic_display,
    })

# ==================== VIRTUAL INTERVIEW & MENTORSHIP ====================
@login_required
def start_manual_meet(request):
    if request.method == 'POST':
        title = request.POST.get('title', 'IntelliPrep Mock Interview')
        scheduled_time_str = request.POST.get('scheduled_time')

        if scheduled_time_str:
            try:
                # Parse datetime
                dt = datetime.strptime(scheduled_time_str, '%Y-%m-%dT%H:%M')
                # Format for Google Meet (ISO 8601)
                start_time = dt.strftime('%Y%m%dT%H%M%SZ')
                
                # Encode title
                encoded_title = urllib.parse.quote(title)
                
                # Create scheduled meet link (Google Meet doesn't support direct scheduling via URL, but we can simulate)
                # Best we can do: open Meet with title pre-filled
                meet_link = f"https://meet.google.com/new?title={encoded_title}"
                
                # You could save this scheduled time to a model later for reminders
                
                messages.success(request, f"Scheduled interview '{title}' created! Use the link below at the scheduled time.")
                
                return render(request, 'question_gen/start_manual_meet.html', {
                    'meet_link': meet_link
                })
            except ValueError:
                messages.error(request, "Invalid date/time format.")
        else:
            messages.error(request, "Please select a date and time.")

    return render(request, 'question_gen/start_manual_meet.html')

def top_performers(request):
    return render(request, 'question_gen/top_performers.html', {
        'users': HIGH_PACKAGE_USERS
    })


@login_required
def user_profile(request, user_id):
    try:
        interviewer = User.objects.get(id=user_id, user_type='interviewer')
    except User.DoesNotExist:
        messages.error(request, "Interviewer not found.")
        return redirect('landing')

    shared_file_data = None
    file_name = None
    request_success = False

    if request.method == 'POST':
        if 'document' in request.FILES:
            # Existing document sharing code...
            uploaded_file = request.FILES['document']
            file_name = uploaded_file.name
            file_content = uploaded_file.read()
            base64_encoded = base64.b64encode(file_content).decode('utf-8')
            mime_type = uploaded_file.content_type or 'application/octet-stream'
            shared_file_data = f"data:{mime_type};base64,{base64_encoded}"
            messages.success(request, f"'{file_name}' ready to share!")

        elif 'schedule_request' in request.POST:
            requested_date = request.POST['requested_date']
            message = request.POST.get('message', '')

            # Create request
            InterviewRequest.objects.create(
                student=request.user,
                interviewer=interviewer,
                requested_date=requested_date,
                message=message
            )
            request_success = True
            messages.success(request, "Interview request sent! Mentor will be notified.")

    return render(request, 'question_gen/user_profile.html', {
        'interviewer': interviewer,
        'shared_file_data': shared_file_data,
        'file_name': file_name,
        'request_success': request_success
    })

@login_required
def accept_request(request, request_id):
    req = get_object_or_404(InterviewRequest, id=request_id, interviewer=request.user)
    req.status = 'accepted'
    req.save()
    messages.success(request, "Interview request accepted!")
    return redirect('landing')

@login_required
def reject_request(request, request_id):
    req = get_object_or_404(InterviewRequest, id=request_id, interviewer=request.user)
    req.status = 'rejected'
    req.save()
    messages.success(request, "Interview request rejected.")
    return redirect('landing')

@login_required
def chat_view(request, user_id):
    other_user = get_object_or_404(User, id=user_id)

    # Security: only allow chat between student and interviewer
    if not (
        (request.user.user_type == 'student' and other_user.user_type == 'interviewer') or
        (request.user.user_type == 'interviewer' and other_user.user_type == 'student')
    ):
        messages.error(request, "You can only chat with mentors/students.")
        return redirect('landing')

    if request.method == 'POST':
        message_text = request.POST.get('message', '').strip()
        if message_text:
            ChatMessage.objects.create(
                sender=request.user,
                receiver=other_user,
                message=message_text
            # Do NOT set timestamp here — let default=timezone.now handle it
            )
            messages.success(request, "Message sent!")

    # Correct query: fetch all messages between the two users, regardless of who is viewing
    chat_history = ChatMessage.objects.filter(
        models.Q(sender=request.user, receiver=other_user) |
        models.Q(sender=other_user, receiver=request.user)
    ).order_by('timestamp')

    return render(request, 'question_gen/chat.html', {
        'other_user': other_user,
        'messages': chat_history
    })

@login_required  # or not, if contact is public
def contact_request(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        message = request.POST.get('message')

        ContactMessage.objects.create(
            name=name,
            email=email,
            message=message
        )
        messages.success(request, "Thank you! Your message has been sent successfully. We'll get back to you soon.")
        
        return redirect('landing')  # ← FIXED: redirect to landing page

    return redirect('landing')  # If GET request, just go to landing