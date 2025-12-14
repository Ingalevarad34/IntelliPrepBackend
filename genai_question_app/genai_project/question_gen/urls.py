from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('select-topic/', views.select_topic, name='select_topic'),
    path('quiz/<str:topic>/', views.quiz_view, name='quiz_view'),  # Updated name
    path('top-performers/', views.top_performers, name='top_performers'),
    path('profile/<int:user_id>/', views.user_profile, name='user_profile'),
    path('meet/start/', views.start_manual_meet, name='start_manual_meet'),
]