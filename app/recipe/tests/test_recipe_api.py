import os
import tempfile
from PIL import Image
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Recipe,
    Tag,
    Ingredient,
)

from recipe.serializers import (
    RecipeSerializer,
    RecipeDetailSerializer,
)

RECIPES_URL = reverse('recipe:recipe-list')


def detail_url(recipe_id):
    return reverse('recipe:recipe-detail', args=[recipe_id])


def image_upload_url(recipe_id):
    return reverse('recipe:recipe-upload-image', args=[recipe_id])


def create_recipe(user, **params):
    defaults = {
        'title': 'Sample Recipe Title',
        'time_minutes': 22,
        'price': Decimal('5.25'),
        'description': 'Sample Description',
        'link': 'http://example.com/recipe.pdf',
    }

    defaults.update(params)

    recipe = Recipe.objects.create(user=user, **defaults)
    return recipe


def create_tag(user, **params):
    return Tag.objects.create(user=user, **params)


def create_ingredient(user, **params):
    return Ingredient.objects.create(user=user, **params)


def create_user(email='testuser@example.com',
                password='testpass123'):
    return get_user_model().objects.create_user(email, password)


class PublicRecipeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        res = self.client.get(RECIPES_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateRecipeAPITests(TestCase):
    def setUp(self):
        self.user = create_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_recipe(self):
        create_recipe(user=self.user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPES_URL)
        recipes = Recipe.objects.all().order_by('-id')
        serializer = RecipeSerializer(recipes, many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        other_user = create_user('otheruser@example.com')

        create_recipe(user=other_user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPES_URL)
        recipes = Recipe.objects.filter(user=self.user)
        serializer = RecipeSerializer(recipes, many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_get_recipe_detail(self):
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.get(url)

        serializer = RecipeDetailSerializer(recipe)
        self.assertEqual(res.data, serializer.data)

    def test_create_recipe(self):
        payload = {
            'title': 'Sample Recipe',
            'price': Decimal('5.99'),
            'time_minutes': 30,
        }

        res = self.client.post(RECIPES_URL, payload)
        recipe = Recipe.objects.get(id=res.data['id'])

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_partial_update(self):
        original_link = 'http://example.com/recipe_original.pdf'
        recipe = create_recipe(
            user=self.user,
            title='Sample Recipe Title',
            link=original_link,
        )

        payload = {'title': 'New Recipe Title'}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload)
        recipe.refresh_from_db()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.title, payload['title'])
        self.assertEqual(recipe.link, original_link)
        self.assertEqual(recipe.user, self.user)

    def test_full_update(self):
        recipe = create_recipe(
            user=self.user,
            title='Sample Recipe Title',
            description='Sample Recipe Description',
            link='http://example.com/recipe_original.pdf',
        )

        payload = {
            'title': 'New Recipe Title',
            'description': 'New Recipe Description',
            'link': 'http://example.com/recipe_new.pdf',
            'price': Decimal('2.50'),
            'time_minutes': 10,
        }

        url = detail_url(recipe.id)
        res = self.client.put(url, payload)
        recipe.refresh_from_db()

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_update_user_returns_error(self):
        other_user = create_user('otheruser@example.com')
        recipe = create_recipe(user=self.user)
        payload = {'user': other_user}

        url = detail_url(recipe.id)
        self.client.patch(url, payload)
        recipe.refresh_from_db()

        self.assertEqual(recipe.user, self.user)

    def test_delete_recipe(self):
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recipe.objects.filter(id=recipe.id).exists())

    def test_delete_other_users_recipe_error(self):
        other_user = create_user('otheruser@example.com')
        recipe = create_recipe(user=other_user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Recipe.objects.filter(id=recipe.id).exists())

    def test_create_recipe_with_new_tags(self):
        payload = {
            'title': 'Thai Prawn Curry',
            'price': Decimal('2.50'),
            'time_minutes': 30,
            'tags': [{'name': 'Thai'}, {'name': 'Dinner'}],
        }

        res = self.client.post(RECIPES_URL, payload, format='json')
        recipes = Recipe.objects.filter(user=self.user)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(recipes.count(), 1)
        self.assertEqual(recipes[0].tags.count(), 2)

        for tag in payload['tags']:
            exists = recipes[0].tags.filter(
                name=tag['name'],
                user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_existing_tags(self):
        tag_indian = Tag.objects.create(user=self.user, name='Indian')

        payload = {
            'title': 'Pongal',
            'time_minutes': 60,
            'price': Decimal('4.50'),
            'tags': [{'name': 'Indian'}, {'name': 'Breakfast'}],
        }

        res = self.client.post(RECIPES_URL, payload, format='json')
        recipes = Recipe.objects.filter(user=self.user)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(recipes.count(), 1)
        self.assertEqual(recipes[0].tags.count(), 2)
        self.assertIn(tag_indian, recipes[0].tags.all())

        for tag in payload['tags']:
            exists = recipes[0].tags.filter(
                name=tag['name'],
                user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_update_recipe_create_tag(self):
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        payload = {'tags': [{'name': 'Lunch'}]}
        res = self.client.patch(url, payload, format='json')

        new_tag = Tag.objects.get(user=self.user, name='Lunch')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(new_tag, recipe.tags.all())

    def test_update_recipe_assign_tag(self):
        tag_breakfast = Tag.objects.create(user=self.user, name='Breakfast')
        tag_lunch = Tag.objects.create(user=self.user, name='Lunch')

        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag_breakfast)

        url = detail_url(recipe.id)
        payload = {'tags': [{'name': 'Lunch'}]}
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn(tag_breakfast, recipe.tags.all())
        self.assertIn(tag_lunch, recipe.tags.all())

    def test_clear_all_tags(self):
        tag = Tag.objects.create(user=self.user, name='Dessert')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag)

        payload = {'tags': []}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.tags.count(), 0)

    def test_create_recipe_with_new_ingredients(self):
        payload = {
            'title': 'Cauliflower Tacos',
            'price': Decimal('4.30'),
            'time_minutes': 60,
            'ingredients': [{'name': 'Cauliflower'}, {'name': 'Salt'}],
        }

        res = self.client.post(RECIPES_URL, payload, format='json')
        recipes = Recipe.objects.filter(user=self.user)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(recipes.count(), 1)
        self.assertEqual(recipes[0].ingredients.count(), 2)

        for ingredient in payload['ingredients']:
            exists = recipes[0].ingredients.filter(
                name=ingredient['name'],
                user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_existing_ingredients(self):
        ingredient = Ingredient.objects.create(user=self.user, name='Lemon')

        payload = {
            'title': 'Vietnamese Soup',
            'time_minutes': 25,
            'price': Decimal('2.55'),
            'ingredients': [{'name': 'Lemon'}, {'name': 'Fish Sauce'}],
        }

        res = self.client.post(RECIPES_URL, payload, format='json')
        recipes = Recipe.objects.filter(user=self.user)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(recipes.count(), 1)
        self.assertEqual(recipes[0].ingredients.count(), 2)
        self.assertIn(ingredient, recipes[0].ingredients.all())

        for ingredient in payload['ingredients']:
            exists = recipes[0].ingredients.filter(
                name=ingredient['name'],
                user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_update_recipe_create_ingredient(self):
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        payload = {'ingredients': [{'name': 'Limes'}]}
        res = self.client.patch(url, payload, format='json')

        new_ingredient = Ingredient.objects.get(user=self.user, name='Limes')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(new_ingredient, recipe.ingredients.all())

    def test_update_recipe_assign_ingredient(self):
        ingredient_pepper = Ingredient.objects.create(
            user=self.user, name='Pepper')
        ingredient_chili = Ingredient.objects.create(
            user=self.user, name='Chili')

        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient_pepper)

        url = detail_url(recipe.id)
        payload = {'ingredients': [{'name': 'Chili'}]}
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn(ingredient_pepper, recipe.ingredients.all())
        self.assertIn(ingredient_chili, recipe.ingredients.all())

    def test_clear_all_ingredients(self):
        ingredient = Ingredient.objects.create(user=self.user, name='Kulfa')
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient)

        payload = {'ingredients': []}
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.ingredients.count(), 0)

    def test_filter_by_tags(self):
        r1 = create_recipe(self.user, title="Thai Vegetable Curry")
        r2 = create_recipe(self.user, title="Aubergine with Tahini")
        r3 = create_recipe(self.user, title="Fish and Chips")
        t1 = create_tag(self.user, name="Vegetarian")
        t2 = create_tag(self.user, name="Vegan")
        r1.tags.add(t1)
        r2.tags.add(t2)

        params = {"tags": f"{t1.id},{t2.id}"}
        res = self.client.get(RECIPES_URL, params)

        s1 = RecipeSerializer(r1)
        s2 = RecipeSerializer(r2)
        s3 = RecipeSerializer(r3)

        self.assertIn(s1.data, res.data)
        self.assertIn(s2.data, res.data)
        self.assertNotIn(s3.data, res.data)

    def test_filter_by_ingredients(self):
        r1 = create_recipe(self.user, title="Thai Vegetable Curry")
        r2 = create_recipe(self.user, title="Aubergine with Tahini")
        r3 = create_recipe(self.user, title="Fish and Chips")
        in1 = create_ingredient(self.user, name="Lettuce")
        in2 = create_ingredient(self.user, name="Sugar")
        r1.ingredients.add(in1)
        r2.ingredients.add(in2)

        params = {"ingredients": f"{in1.id},{in2.id}"}
        res = self.client.get(RECIPES_URL, params)

        s1 = RecipeSerializer(r1)
        s2 = RecipeSerializer(r2)
        s3 = RecipeSerializer(r3)

        self.assertIn(s1.data, res.data)
        self.assertIn(s2.data, res.data)
        self.assertNotIn(s3.data, res.data)


class ImageUploadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            'user@example.com',
            'password123',
        )
        self.client.force_authenticate(self.user)
        self.recipe = create_recipe(user=self.user)

    def tearDown(self):
        self.recipe.image.delete()

    def test_upload_image(self):
        url = image_upload_url(self.recipe.id)
        with tempfile.NamedTemporaryFile(suffix='.jpg') as image_file:
            img = Image.new('RGB', (10, 10))
            img.save(image_file, format='JPEG')
            image_file.seek(0)
            payload = {'image': image_file}
            res = self.client.post(url, payload, format='multipart')

        self.recipe.refresh_from_db()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('image', res.data)
        self.assertTrue(os.path.exists(self.recipe.image.path))

    def test_upload_image_bad_request(self):
        url = image_upload_url(self.recipe.id)
        payload = {'image': 'notreallyanimage'}
        res = self.client.post(url, payload, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
