from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Recipe,
    Ingredient,
)

from recipe.serializers import IngredientSerializer


INGREDIENTS_URL = reverse('recipe:ingredient-list')


def detail_url(ingredient_id):
    return reverse('recipe:ingredient-detail', args=[ingredient_id])


def create_user(email='testuser@example.com',
                password='testpass123'):
    return get_user_model().objects.create_user(email, password)


def create_ingredient(user, **params):
    return Ingredient.objects.create(user=user, **params)


class PublicIngredientsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        res = self.client.get(INGREDIENTS_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateRecipeAPITests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_recipe(self):
        create_ingredient(user=self.user, name="Kale")
        create_ingredient(user=self.user, name="Vanilla")

        res = self.client.get(INGREDIENTS_URL)
        ingredients = Ingredient.objects.all().order_by('-name')
        serializer = IngredientSerializer(ingredients, many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        other_user = create_user('otheruser@example.com')

        create_ingredient(user=other_user, name="Salt")
        ingredient = create_ingredient(user=self.user, name="Pepper")

        res = self.client.get(INGREDIENTS_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['id'], ingredient.id)
        self.assertEqual(res.data[0]['name'], ingredient.name)

    def test_update_ingredient(self):
        ingredient = create_ingredient(user=self.user, name="Cilantro")

        url = detail_url(ingredient.id)
        payload = {'name': 'Coriander'}
        res = self.client.patch(url, payload)

        ingredient.refresh_from_db()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(ingredient.name, payload['name'])

    def test_delete_ingredient(self):
        ingredient = create_ingredient(user=self.user, name="Lettuce")

        url = detail_url(ingredient.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Ingredient.objects.filter(id=ingredient.id).exists())

    def test_filter_ingredients_assigned_to_recipe(self):
        in1 = create_ingredient(self.user, name='Apples')
        in2 = create_ingredient(self.user, name='Turkey')
        recipe = Recipe.objects.create(
            title='Apple Crumble',
            price=Decimal('4.50'),
            time_minutes=5,
            user=self.user,
        )
        recipe.ingredients.add(in1)

        res = self.client.get(INGREDIENTS_URL, {'assigned_only': 1})

        s1 = IngredientSerializer(in1)
        s2 = IngredientSerializer(in2)

        self.assertIn(s1.data, res.data)
        self.assertNotIn(s2.data, res.data)

    def test_filtered_ingredients_unique(self):
        ing = create_ingredient(self.user, name='Eggs')
        create_ingredient(self.user, name='Lentils')
        recipe1 = Recipe.objects.create(
            title='Eggs Benedict',
            price=Decimal('7.00'),
            time_minutes=60,
            user=self.user,
        )
        recipe2 = Recipe.objects.create(
            title='Herb Eggs',
            price=Decimal('4.00'),
            time_minutes=20,
            user=self.user,
        )
        recipe1.ingredients.add(ing)
        recipe2.ingredients.add(ing)

        res = self.client.get(INGREDIENTS_URL, {'assigned_only': 1})

        self.assertEqual(len(res.data), 1)
