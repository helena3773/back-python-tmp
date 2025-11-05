import os
import random

from flask_restful import Resource
import polars as pl
import requests
from flask import request
import numpy as np
from dotenv import load_dotenv
load_dotenv()

SPRING_REQUEST_URL = os.getenv("SPRING_URL")

class FoodRecommend(Resource):
    def get(self):
        userId = request.args.get("id")
        meal_types = ["아침", "점심", "저녁"]
        recommended_foods = []
        for meal_type in meal_types:
            user_meals = fetch_user_meals(userId)
            recommendation = recommend_meal(user_meals, meal_type)
            if not recommendation:
                continue

            recommended_foods.append({
                "MEAL_TYPE": meal_type,
                "RECOMMEND_FOOD": recommendation["RECOMMEND_FOOD"],
                "RECIPECODE": recommendation["RECIPECODE"]
            })

            save_recommendation(userId, meal_type, recommendation["RECOMMEND_FOOD"], recommendation["RECIPECODE"])

            return {"recommended_foods": recommended_foods}, 200
        return

def fetch_user_meals(userId):
    """
    사용자의 식사 데이터 요청
    :param userId: 사용자 id
    :return: 사용자 식사 데이터
    """
    try:
        res = requests.get(f"{SPRING_REQUEST_URL}/userMeals", params={"id": userId}, timeout=5)
        res.raise_for_status()
        data = res.json()
        if not data or len(data) == 0:
            print("사용자 데이터 없음 -> 기본 데이터 셋 사용")
            return fetch_default_food()
        return data
    except Exception as e:
        print("사용자 식사 데이터 요청 실패", e)
        return data

def fetch_default_food():
    """
    사용자의 식사기록이 없을 때
    :return: 기본 음식 데이터
    """
    return [{
        "EATING_FOODNAME": "닭가슴살 샐러드",
        "RECIPECODE": "R0001",
        "MEALTYPE": "점심",
        "INGREDIENT": ["닭가슴살", "오이", "양상추"],
        "CALORIE": 250, "PROTEIN": 30, "FAT": 4, "CARBOHYDRATE": 10
    }]

def recommend_meal(user_meals, meal_type):
    """
    추천 음식
    :param user_meals: 사용자 식사 데이터
    :param meal_type: 아침, 점심, 저녁 중 하나
    :return: 추천 음식 정보
    """
    filtered = [m for m in user_meals if m.get("MEALTYPE") == meal_type]
    if not filtered:
        default_foods = fetch_default_food()
        return random.choice(default_foods)

    # 재료 백터 구성
    ingredients = sorted(set(ing for m in filtered for ing in (m.get("INGREDIENT") or [])))
    if not ingredients:
        return random.choice(filtered)

    ing_to_idx = {ing: i for i, ing in enumerate(ingredients)}

    meal_vectors, nutrition_vectors = [], []

    for m in filtered:
        vec_ing = np.zeros(len(ingredients))
        for ing in (m.get("INGREDIENT") or []):
            if ing in ing_to_idx:
                vec_ing[ing_to_idx[ing]] = 1

        vec_nut = np.array([
            m.get("CALORIE", 0.0),
            m.get("PROTEIN", 0.0),
            m.get("FAT", 0.0),
            m.get("CARBOHYDRATE", 0.0)
        ], dtype=float)

        meal_vectors.append(vec_ing)
        nutrition_vectors.append(vec_nut)

    meal_vectors = np.array(meal_vectors)
    nutrition_vectors = np.array(nutrition_vectors)

    # 영양소 정규화
    if nutrition_vectors.shape[0] > 0:
        min_val = nutrition_vectors.min(axis=0)
        ptp_val = nutrition_vectors.ptp(axis=0)
        ptp_val[ptp_val == 0] = 1
        nutrition_vectors = (nutrition_vectors - min_val) / ptp_val

    # 두 벡터 결합 + 유사도 계산
    final_vectors = np.concatenate([meal_vectors, nutrition_vectors], axis=1)
    norms = np.linalg.norm(final_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = final_vectors / norms
    sim = np.dot(normed, normed.T)

    scores = sim.sum(axis=1)
    best_idx = int(np.argmax(scores))

    return {
        "RECOMMEND_FOOD": filtered[best_idx]["EATING_FOODNAME"],
        "RECIPECODE": filtered[best_idx]["RECIPECODE"],
    }

def save_recommendation(userId, meal_type, food, recipe_code):
    """
    SPRING BOOT API로 추천 결과 저장 요청
    :param userId: 사용자 아이디
    :param meal_type: 아침, 점심, 저녁 중 하나
    :param food: 음식
    :param recipe_code: 음식 코드
    :return:
    """
    try:
        res = requests.post(f"{SPRING_REQUEST_URL}/saveRecommendation", json={
            "userId": userId,
            "mealType": meal_type,
            "foodName": food,
            "recipeCode": recipe_code
        }, timeout=5)
        res.raise_for_status()
    except Exception as e:
        print("추천 결과 저장 실패: ", e)