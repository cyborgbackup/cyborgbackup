from django.test import TestCase
import logging

#from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

logger = logging.getLogger('cyborgbackup')
logger.setLevel(logging.CRITICAL)

class CyborgbackupApiTest(APITestCase):
    fixtures = ["tests.json"]
    def test_page_not_found(self):
        response = self.client.get('/notFound', format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_access_api(self):
        url = reverse('api:api_root_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['current_version'], '/api/v1/')

    def test_ui_access_ui(self):
        url = reverse('ui:index')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_api_access_swagger(self):
        url = reverse('api:swagger_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_api_access_login(self):
        url = reverse('api:login')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_api_access_logout(self):
        url = reverse('api:logout')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    def test_api_v1_access_root(self):
        url = reverse('api:api_v1_root_view', kwargs={'version': 'v1'})
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['ping'], '/api/v1/ping/')

    def test_api_v1_access_ping(self):
        url = reverse('api:api_v1_ping_view', kwargs={'version': 'v1'})
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['version'], '1.0')
        self.assertEqual(response.data['ping'], 'pong')

    def test_api_v1_access_config_without_auth(self):
        url = reverse('api:api_v1_config_view', kwargs={'version': 'v1'})
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_api_v1_access_config_with_auth(self):
        url = reverse('api:api_v1_config_view', kwargs={'version': 'v1'})
        user = get_user_model().objects.first()
        self.client.force_login(user)
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['time_zone'], 'UTC')
        self.assertFalse(response.data['debug'])
        self.assertFalse(response.data['sql_debug'])
        self.assertEqual(response.data['version'], '1.0')
