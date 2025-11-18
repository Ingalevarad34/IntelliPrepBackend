from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
import google.generativeai as genai
from django.conf import settings
import re
import PyPDF2  # NEW: For PDF extraction
import os
from io import BytesIO  # For in-memory handling

# Configure the client
genai.configure(api_key=settings.GEMINI_API_KEY)

def landing(request):
    """Landing page with Start Quiz button."""
    return render(request, 'question_gen/landing.html')

def select_topic(request):
    """Topic selection + file upload. Summarize file if uploaded, start quiz."""
    if request.method == 'POST':
        topic = request.POST.get('topic', '')
        document_file = request.FILES.get('document')  # NEW: File handling
        summary = ''  # Default no summary
        
        if document_file:
            try:
                # Extract text from PDF (in-memory)
                pdf_reader = PyPDF2.PdfReader(BytesIO(document_file.read()))
                text = ''
                for page in pdf_reader.pages:
                    text += page.extract_text() + '\n'
                
                # Summarize with Gemini
                model = genai.GenerativeModel('gemini-2.5-flash')
                sum_prompt = f"Summarize the key points from this document text (focus on {topic} if provided): {text[:4000]}"  # Limit text to avoid token overflow
                sum_response = model.generate_content(sum_prompt)
                summary = sum_response.text.strip()
                
                # Optional: Save file temp (for debug; delete after)
                temp_path = os.path.join(settings.TEMP_DIR, document_file.name)
                with open(temp_path, 'wb') as f:
                    for chunk in document_file.chunks():
                        f.write(chunk)
                # os.remove(temp_path)  # Cleanup after summary
                
                messages.success(request, f"Document summarized! ({len(summary)} chars)")
            except Exception as e:
                messages.error(request, f"Error processing document: {str(e)}")
                return render(request, 'question_gen/select_topic.html')
        elif topic in ['java', 'javascript', 'reactjs']:
            # No file: Use topic as before
            pass
        else:
            return JsonResponse({'error': 'Invalid topic or no file'}, status=400)
        
        try:
            # Generate initial question (use summary if available)
            model = genai.GenerativeModel('gemini-2.5-flash')
            base_context = f"Document summary (if any): {summary}. " if summary else ''
            prompt = f"You are a quiz master on {topic} programming. {base_context}Start with a broad, engaging opener question for beginners. Begin with a short compliment like 'Welcome!' then the question (e.g., 'What is {topic}?'). Keep concise."
            response = model.generate_content(prompt)
            full_text = response.text.strip()
            
            # Parse initial
            compliment, question = parse_response(full_text)
            
            # Start session (include summary)
            request.session['history'] = []
            request.session['step'] = 0
            request.session['nest_level'] = 0
            request.session['topic'] = topic or 'Document Content'  # Fallback
            request.session['document_summary'] = summary  # NEW: Store summary
            request.session['current_compliment'] = compliment
            request.session['current_question'] = question
            request.session.modified = True
            return redirect('quiz_view', topic=request.session['topic'])
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return render(request, 'question_gen/select_topic.html')

def parse_response(full_text):
    """Parse API response into compliment and question."""  # Unchanged
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
    """Dynamic quiz: Show question, process answer, nest/branch next."""  # Most unchanged, but add summary to prompts
    if topic != request.session.get('topic', ''):
        messages.error(request, 'Session expired. Start a new quiz.')
        return redirect('landing')
    
    history = request.session.get('history', [])
    step = request.session.get('step', 0)
    nest_level = request.session.get('nest_level', 0)
    max_steps = 10
    summary = request.session.get('document_summary', '')  # NEW: Get summary
    
    if step >= max_steps:
        request.session.clear()
        return render(request, 'question_gen/quiz_end.html', {
            'history': history,
            'topic': topic.replace('-', ' ').title(),
            'total_steps': max_steps,
            'score': len([h for h in history if 'correct' in h.get('feedback', '').lower()]),
            'percentage': round((len([h for h in history if 'correct' in h.get('feedback', '').lower()]) / max_steps) * 100, 1),
            'document_summary': summary  # Pass for end review
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
            
            # Step 1: Judge correctness (include summary)
            context = base_context + '\n'.join([f"Q: {h['question']} A: {h['user_answer']}" for h in history[-3:]])
            judge_prompt = f"Topic: {topic}. {context} Current Q: {current_question} User A: {user_answer}. Is it correct (yes/no)? If no, brief explanation. Output: 'Correct!' or 'Incorrect: [explanation]'."
            judge_response = model.generate_content(judge_prompt)
            feedback = judge_response.text.strip()
            
            # Step 2: Extract keyword/concept (include summary for better recognition)
            extract_prompt = f"{base_context}From user answer '{user_answer}' on {topic}, extract 1 key technical keyword/phrase/acronym (e.g., 'OOP' or 'object oriented' from 'java is object oriented programming language'). Prioritize unexplored terms. Output just the keyword."
            extract_response = model.generate_content(extract_prompt)
            concept = extract_response.text.strip()
            
            # Step 3: Generate next with nesting/branching (include summary)
            if nest_level < 2:
                nest_text = f"Nest deeper on '{concept}' (current level {nest_level + 1})."
                next_level = nest_level + 1
            else:
                full_history = base_context + '\n'.join([f"Q: {h['question']} A: {h['user_answer']} Concept: {h['concept']}" for h in history])
                extract_prompt_branch = f"{full_history}, suggest 1 fresh, unrelated concept/keyword not previously nested. Output just the keyword."
                branch_response = model.generate_content(extract_prompt_branch)
                concept = branch_response.text.strip()
                nest_text = f"Branch to new topic '{concept}' (reset to level 0)."
                next_level = 0
            
            next_prompt = f"You are a quiz master on {topic}. {base_context}{nest_text} Respond engagingly: Start with a compliment on their previous answer (e.g., 'Alright, you've grasped... Fantastic!'), then 'Now, [brief context if needed], [follow-up question on '{concept}']?' Use history: {context}. Keep concise, separate clearly."
            next_response = model.generate_content(next_prompt)
            full_next = next_response.text.strip()
            
            # Parse
            compliment, question = parse_response(full_next)
            
            # Store in history
            history_entry = {
                'question': current_question,
                'user_answer': user_answer,
                'concept': concept,
                'feedback': feedback,
                'nest_level': nest_level,
                'compliment': compliment
            }
            history.append(history_entry)
            
            # Update session
            request.session['history'] = history
            request.session['step'] = step + 1
            request.session['nest_level'] = next_level
            request.session['current_compliment'] = compliment
            request.session['current_question'] = question
            request.session.modified = True
            
            # Feedback message
            if 'correct' in feedback.lower():
                messages.success(request, f"{feedback} Great—{'nesting' if next_level > 0 else 'branching'} into '{concept}'!")
            else:
                messages.error(request, f"{feedback} No worries—{'nesting' if next_level > 0 else 'branching'} into '{concept}' next!")
            
            return redirect('quiz_view', topic=topic)
            
        except Exception as e:
            messages.error(request, f"Error processing answer: {str(e)}")
            return redirect('quiz_view', topic=topic)
    
    # GET: Show compliment ABOVE question
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