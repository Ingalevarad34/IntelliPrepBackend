from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('select-topic/', views.select_topic, name='select_topic'),
    path('quiz/<str:topic>/', views.quiz_view, name='quiz_view'),  # Updated name
]