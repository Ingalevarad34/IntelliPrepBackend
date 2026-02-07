from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('login/', views.user_login, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.user_logout, name='logout'),
    
    # Quiz
    path('select-topic/', views.select_topic, name='select_topic'),
    path('quiz/<str:topic>/', views.quiz_view, name='quiz_view'),
    
    # Virtual Interview
    path('meet/start/', views.start_manual_meet, name='start_manual_meet'),
    
    # Mentor & Chat
    path('top-performers/', views.top_performers, name='top_performers'),
    path('profile/<int:user_id>/', views.user_profile, name='user_profile'),
    path('chat/<int:user_id>/', views.chat_view, name='chat'),
    
    # Interview Request Actions
    path('accept-request/<int:request_id>/', views.accept_request, name='accept_request'),
    path('reject-request/<int:request_id>/', views.reject_request, name='reject_request'),

    #Contact
    path('contact/', views.contact_request, name='contact'),
]