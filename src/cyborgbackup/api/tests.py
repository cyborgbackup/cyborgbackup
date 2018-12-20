from django.test import TestCase
import logging

#from django.urls import reverse
from rest_framework.reverse import reverse
from rest_framework import status
from rest_framework.test import APITestCase

logger = logging.getLogger('cyborgbackup')
logger.setLevel(logging.WARNING)

class CyborgbackupApiTest(APITestCase):
    def test_access_api(self):
        url = reverse('api:api_root_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_not_found(self):
        response = self.client.get('/notFound', format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_access_swagger(self):
        url = reverse('api:swagger_view')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_access_login(self):
        url = reverse('api:login')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_access_logout(self):
        url = reverse('api:logout')
        response = self.client.get(url, format='json')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
