from functools import update_wrapper

from django.contrib.admin import ModelAdmin, AdminSite
from django.urls import reverse, re_path
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.i18n import JSONCatalog
from rest_framework import status
from rest_framework.response import Response

from django_api_admin import views as api_views
from django_api_admin.permissions import IsAdminUser
from django_api_admin.serializers import LoginSerializer, UserSerializer, PasswordChangeSerializer
from rest_framework.exceptions import PermissionDenied

from django_api_admin.views import TranslationCatalogView


class AlreadyRegistered(Exception):
    pass


class NotRegistered(Exception):
    pass


class APIAdminSite(AdminSite):
    """
    Encapsulates an instance of the django admin application.

    todo override register() to register a custom model admin.
    """
    login_serializer = None
    user_serializer = None
    password_change_serializer = None
    final_catch_all_view = False
    default_permissions = [IsAdminUser, ]

    def __init__(self, default_admin_class=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_admin_class = default_admin_class or ModelAdmin

    def api_admin_view(self, view, cacheable=False):
        """
        Adds csrf token protection and caching to views.
        """

        def inner(request, *args, **kwargs):
            return view(request, *args, **kwargs)

        if not cacheable:
            inner = never_cache(inner)
        if not getattr(view, 'csrf_exempt', False):
            inner = csrf_protect(inner)
        return update_wrapper(inner, view)

    def get_urls(self):
        # from django.contrib.contenttypes import views as contenttype_views
        from django.urls import path, include

        def wrap(view, cacheable=False):
            def wrapper(*args, **kwargs):
                return self.api_admin_view(view, cacheable)(*args, **kwargs)

            wrapper.admin_site = self
            return update_wrapper(wrapper, view)

        # Admin-site-wide views.
        urlpatterns = [
            path('', wrap(self.index), name='index'),
            path('login/', self.login, name='login'),
            path('logout/', wrap(self.logout), name='logout'),
            path('password_change/', wrap(self.password_change, cacheable=True), name='password_change'),
            path(
                'password_change/done/',
                wrap(self.password_change_done, cacheable=True),
                name='password_change_done',
            ),
            path('autocomplete/', wrap(self.autocomplete_view), name='autocomplete'),
            path('language_catalog/', wrap(self.language_catalog, cacheable=True), name='language_catalog'),
            # todo understand what the view on site view does.
            # path('r/<int:content_type_id>/<path:object_id>/',wrap(contenttype_views.shortcut),name='view_on_site',),
        ]

        # Add in each model's views, and create a list of valid URLS for the
        # app_index
        valid_app_labels = []
        for model, model_admin in self._registry.items():
            urlpatterns += [
                path('%s/%s/' % (model._meta.app_label, model._meta.model_name), include(model_admin.urls)),
            ]
            if model._meta.app_label not in valid_app_labels:
                valid_app_labels.append(model._meta.app_label)

        # If there were ModelAdmins registered, we should have a list of app
        # labels for which we need to allow access to the app_index view,
        if valid_app_labels:
            regex = r'^(?P<app_label>' + '|'.join(valid_app_labels) + ')/$'
            urlpatterns += [
                re_path(regex, wrap(self.app_index), name='app_list'),
            ]

        # todo understand what final catch all view means
        if self.final_catch_all_view:
            urlpatterns.append(re_path(r'(?P<url>.*)$', wrap(self.catch_all_view)))

        return urlpatterns

    # todo choose the best place to add login permissions
    def login(self, request, extra_context=None):
        defaults = {
            'serializer_class': self.login_serializer or LoginSerializer,
            'user_serializer_class': self.user_serializer or UserSerializer
        }
        return api_views.LoginView.as_view(**defaults)(request, extra_context)

    def logout(self, request, extra_context=None):
        defaults = {
            'user_serializer_class': self.user_serializer or UserSerializer,
            'permission_classes': self.default_permissions,
        }
        return api_views.LogoutView.as_view(**defaults)(request, extra_context)

    def password_change(self, request, extra_context=None):
        defaults = {
            'serializer_class': self.password_change_serializer or PasswordChangeSerializer,
            'permission_classes': self.default_permissions,
        }
        return api_views.PasswordChangeView.as_view(**defaults)(request, extra_context)

    def index(self, request, extra_context=None):
        defaults = {
            'permission_classes': self.default_permissions,
        }
        return api_views.IndexView.as_view(**defaults)(request, self, extra_context)

    def app_index(self, request, app_label, extra_context=None):
        defaults = {
            'permission_classes': self.default_permissions,
        }
        return api_views.AppIndexView.as_view(**defaults)(request, self, app_label, extra_context)

    # todo understand i18n_javascript and language catalog means.
    def language_catalog(self, request, extra_context=None):
        """
        Returns the selected language catalog as JsonObject.
        """
        defaults = {
            'permission_classes': self.default_permissions,
        }
        return TranslationCatalogView.as_view(**defaults)(request, packages=['django_api_admin'])


site = APIAdminSite()