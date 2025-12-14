from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
import google.generativeai as genai
from django.conf import settings
import re
import PyPDF2
import os
from io import BytesIO
import datetime
import urllib.parse  # For URL encoding
import base64
from django.http import HttpResponse
# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)

# ==================== QUIZ VIEWS ====================

# Mock data for high-package users (replace with DB later)
HIGH_PACKAGE_USERS = [
    {
        'id': 1,
        'name': 'Aman Gupta',
        'package': '45 LPA',
        'company': 'Google',
        'role': 'Senior Software Engineer',
        'skills': 'System Design, Java, Microservices',
        'bio': 'Ex-Amazon, helped 200+ students crack FAANG interviews',
        'image': 'https://randomuser.me/api/portraits/men/32.jpg'
    },
    {
        'id': 2,
        'name': 'Priya Sharma',
        'package': '52 LPA',
        'company': 'Microsoft',
        'role': 'Principal Engineer',
        'skills': 'React, TypeScript, Cloud Architecture',
        'bio': 'Mentored 150+ students to top tech roles',
        'image': 'https://randomuser.me/api/portraits/women/44.jpg'
    },
    {
        'id': 3,
        'name': 'Rahul Verma',
        'package': '38 LPA',
        'company': 'Atlassian',
        'role': 'Staff Engineer',
        'skills': 'Backend, Distributed Systems, Leadership',
        'bio': 'Ex-Flipkart, passionate about teaching DSA',
        'image': 'https://randomuser.me/api/portraits/men/45.jpg'
    },
]

def landing(request):
    """Landing page with Start Quiz and Meet buttons."""
    return render(request, 'question_gen/landing.html')

def select_topic(request):
    """Topic selection + file upload. Summarize file if uploaded, start quiz."""
    if request.method == 'POST':
        topic = request.POST.get('topic', '')
        document_file = request.FILES.get('document')
        summary = ''
        
        if document_file:
            try:
                pdf_reader = PyPDF2.PdfReader(BytesIO(document_file.read()))
                text = ''
                for page in pdf_reader.pages:
                    text += page.extract_text() + '\n'
                
                model = genai.GenerativeModel('gemini-2.5-flash')
                sum_prompt = f"Summarize the key points from this document text (focus on {topic} if provided): {text[:4000]}"
                sum_response = model.generate_content(sum_prompt)
                summary = sum_response.text.strip()
                
                messages.success(request, f"Document summarized! ({len(summary)} chars)")
            except Exception as e:
                messages.error(request, f"Error processing document: {str(e)}")
                return render(request, 'question_gen/select_topic.html')
        elif topic not in ['java', 'javascript', 'reactjs']:
            return JsonResponse({'error': 'Invalid topic or no file'}, status=400)
        
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            base_context = f"Document summary (if any): {summary}. " if summary else ''
            prompt = f"You are a quiz master on {topic} programming. {base_context}Start with a broad, engaging opener question for beginners. Begin with a short compliment like 'Welcome!' then the question. Keep concise."
            response = model.generate_content(prompt)
            full_text = response.text.strip()
            
            compliment, question = parse_response(full_text)
            
            request.session['history'] = []
            request.session['step'] = 0
            request.session['nest_level'] = 0
            request.session['topic'] = topic or 'Document Content'
            request.session['document_summary'] = summary
            request.session['current_compliment'] = compliment
            request.session['current_question'] = question
            request.session.modified = True
            return redirect('quiz_view', topic=request.session['topic'])
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return render(request, 'question_gen/select_topic.html')

def parse_response(full_text):
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
    elif re.search(r'\?', full_text):
        split_idx = full_text.find('?') + 1
        compliment = full_text[:split_idx].rstrip('?').strip()
        question = full_text[split_idx:].strip()
    else:
        compliment = ''
        question = full_text
    question = re.sub(r'`history:`', 'Based on our discussion:', question)
    return compliment, question

def quiz_view(request, topic):
    if topic != request.session.get('topic', ''):
        messages.error(request, 'Session expired. Start a new quiz.')
        return redirect('landing')
    
    history = request.session.get('history', [])
    step = request.session.get('step', 0)
    nest_level = request.session.get('nest_level', 0)
    max_steps = 10
    summary = request.session.get('document_summary', '')
    
    if step >= max_steps:
        request.session.clear()
        return render(request, 'question_gen/quiz_end.html', {
            'history': history,
            'topic': topic.replace('-', ' ').title(),
            'total_steps': max_steps,
            'score': len([h for h in history if 'correct' in h.get('feedback', '').lower()]),
            'percentage': round((len([h for h in history if 'correct' in h.get('feedback', '').lower()]) / max_steps) * 100, 1),
            'document_summary': summary
        })
    
    current_compliment = request.session.get('current_compliment', '')
    current_question = request.session.get('current_question', 'What is in the document?')
    
    if request.method == 'POST':
        user_answer = request.POST.get('answer', '').strip()
        if not user_answer:
            messages.error(request, "No answer provided. Please try again.")
            return redirect('quiz_view', topic=topic)
        
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            base_context = f"Document summary: {summary}. " if summary else ''
            context = base_context + '\n'.join([f"Q: {h['question']} A: {h['user_answer']}" for h in history[-3:]])
            judge_prompt = f"Topic: {topic}. {context} Current Q: {current_question} User A: {user_answer}. Is it correct (yes/no)? If no, brief explanation. Output: 'Correct!' or 'Incorrect: [explanation]'."
            judge_response = model.generate_content(judge_prompt)
            feedback = judge_response.text.strip()
            
            extract_prompt = f"{base_context}From user answer '{user_answer}' on {topic}, extract 1 key technical keyword/phrase/acronym. Prioritize unexplored terms. Output just the keyword."
            extract_response = model.generate_content(extract_prompt)
            concept = extract_response.text.strip()
            
            if nest_level < 2:
                nest_text = f"Nest deeper on '{concept}' (current level {nest_level + 1})."
                next_level = nest_level + 1
            else:
                full_history = base_context + '\n'.join([f"Q: {h['question']} A: {h['user_answer']} Concept: {h['concept']}" for h in history])
                branch_prompt = f"{full_history}, suggest 1 fresh, unrelated concept/keyword not previously nested. Output just the keyword."
                branch_response = model.generate_content(branch_prompt)
                concept = branch_response.text.strip()
                nest_text = f"Branch to new topic '{concept}' (reset to level 0)."
                next_level = 0
            
            next_prompt = f"You are a quiz master on {topic}. {base_context}{nest_text} Respond engagingly: Start with a compliment on their previous answer, then 'Now, [follow-up question on '{concept}']?' Use history: {context}. Keep concise, separate clearly."
            next_response = model.generate_content(next_prompt)
            full_next = next_response.text.strip()
            
            compliment, question = parse_response(full_next)
            
            history_entry = {
                'question': current_question,
                'user_answer': user_answer,
                'concept': concept,
                'feedback': feedback,
                'nest_level': nest_level,
                'compliment': compliment
            }
            history.append(history_entry)
            
            request.session['history'] = history
            request.session['step'] = step + 1
            request.session['nest_level'] = next_level
            request.session['current_compliment'] = compliment
            request.session['current_question'] = question
            request.session.modified = True
            
            if 'correct' in feedback.lower():
                messages.success(request, f"{feedback} Great—{'nesting' if next_level > 0 else 'branching'} into '{concept}'!")
            else:
                messages.error(request, f"{feedback} No worries—{'nesting' if next_level > 0 else 'branching'} into '{concept}' next!")
            
            return redirect('quiz_view', topic=topic)
        except Exception as e:
            messages.error(request, f"Error processing answer: {str(e)}")
            return redirect('quiz_view', topic=topic)
    
    topic_display = topic.replace('-', ' ').title()
    return render(request, 'question_gen/quiz_question.html', {
        'compliment': current_compliment,
        'question': current_question,
        'step': step + 1,
        'total': max_steps,
        'nest_level': nest_level,
        'history': history,
        'topic': topic_display,
    })

# ==================== SIMPLE MANUAL MEET GENERATOR (NO OAUTH!) ====================
def start_manual_meet(request):
    """Generate an instant Google Meet link without login."""
    if request.method == 'POST':
        title = request.POST.get('title', 'IntelliPrep Virtual Interview')
        encoded_title = urllib.parse.quote(title)
        
        meet_link = f"https://meet.google.com/new?title={encoded_title}"
        
        messages.success(request, f"Virtual Interview Meet Ready!<br><br>"
                                 f"<a href='{meet_link}' target='_blank' style='font-size: 1.4em; color: #4CAF50; font-weight: bold;'>"
                                 f"🔗 Click Here to Join the Meet</a><br><br>"
                                 f"<small>Share this link with the interviewer!</small>")
        return redirect('landing')
    
    return render(request, 'question_gen/start_manual_meet.html')


def top_performers(request):
    """Show list of high-package users on home page"""
    return render(request, 'question_gen/top_performers.html', {
        'users': HIGH_PACKAGE_USERS
    })

def user_profile(request, user_id):
    user = next((u for u in HIGH_PACKAGE_USERS if u['id'] == user_id), None)
    if not user:
        messages.error(request, "User not found")
        return redirect('landing')

    shared_file_data = None
    file_name = None

    if request.method == 'POST' and 'document' in request.FILES:
        uploaded_file = request.FILES['document']
        file_name = uploaded_file.name
        
        # Read file content and encode to base64 for direct link
        file_content = uploaded_file.read()
        base64_encoded = base64.b64encode(file_content).decode('utf-8')
        
        # Create data URL for direct download
        mime_type = uploaded_file.content_type or 'application/octet-stream'
        shared_file_data = f"data:{mime_type};base64,{base64_encoded}"
        
        messages.success(request, f"'{file_name}' is ready to share! Copy the link below and paste in Meet chat.")

    return render(request, 'question_gen/user_profile.html', {
        'user': user,
        'shared_file_data': shared_file_data,
        'file_name': file_name
    })