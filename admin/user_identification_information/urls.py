from django.conf.urls import url

from . import views

app_name = 'admin'

urlpatterns = [
    url(r'^$', views.UserIdentificationListViewListView.as_view(), name='user_identification_list'),
    url(r'^(?P<guid>[a-z0-9]+)/$', views.UserIdentificationDetailView.as_view(), name='user_identification_detail'),
]
