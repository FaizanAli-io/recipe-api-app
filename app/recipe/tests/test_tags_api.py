from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Recipe,
    Tag,
)

from recipe.serializers import TagSerializer


TAGS_URL = reverse('recipe:tag-list')


def detail_url(tag_id):
    return reverse('recipe:tag-detail', args=[tag_id])


def create_user(email='testuser@example.com',
                password='testpass123'):
    return get_user_model().objects.create_user(email, password)


def create_tag(user, **params):
    return Tag.objects.create(user=user, **params)


class PublicTagsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        res = self.client.get(TAGS_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateRecipeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_user()
        self.client.force_authenticate(self.user)

    def test_retrieve_recipe(self):
        create_tag(user=self.user, name="Vegan")
        create_tag(user=self.user, name="Dessert")

        res = self.client.get(TAGS_URL)
        tags = Tag.objects.all().order_by('-name')
        serializer = TagSerializer(tags, many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        other_user = create_user('otheruser@example.com')

        create_tag(user=other_user, name="Fruity")
        tag = create_tag(user=self.user, name="Comfort Food")

        res = self.client.get(TAGS_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['id'], tag.id)
        self.assertEqual(res.data[0]['name'], tag.name)

    def test_update_tag(self):
        tag = create_tag(user=self.user, name="After Dinner")

        url = detail_url(tag.id)
        payload = {'name': 'Dessert'}
        res = self.client.patch(url, payload)
        tag.refresh_from_db()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(tag.name, payload['name'])

    def test_delete_tag(self):
        tag = create_tag(user=self.user, name="Breakfast")

        url = detail_url(tag.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Tag.objects.filter(id=tag.id).exists())

    def test_filter_tags_assigned_to_recipe(self):
        t1 = create_tag(self.user, name='Breakfast')
        t2 = create_tag(self.user, name='Lunch')
        recipe = Recipe.objects.create(
            title='Green Eggs on Toast',
            price=Decimal('2.50'),
            time_minutes=10,
            user=self.user,
        )
        recipe.tags.add(t1)

        res = self.client.get(TAGS_URL, {'assigned_only': 1})

        s1 = TagSerializer(t1)
        s2 = TagSerializer(t2)

        self.assertIn(s1.data, res.data)
        self.assertNotIn(s2.data, res.data)

    def test_filtered_tags_unique(self):
        tag = create_tag(self.user, name='Breakfast')
        create_tag(self.user, name='Dinner')
        recipe1 = Recipe.objects.create(
            title='Pancakes',
            price=Decimal('5.00'),
            time_minutes=5,
            user=self.user,
        )
        recipe2 = Recipe.objects.create(
            title='Porridge',
            price=Decimal('2.00'),
            time_minutes=3,
            user=self.user,
        )
        recipe1.tags.add(tag)
        recipe2.tags.add(tag)

        res = self.client.get(TAGS_URL, {'assigned_only': 1})

        self.assertEqual(len(res.data), 1)
