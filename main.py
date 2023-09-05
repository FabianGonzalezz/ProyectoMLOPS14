import pandas as pd
import numpy as np
from textblob import TextBlob
from sklearn.metrics.pairwise import cosine_similarity
import ast
from fastapi import FastAPI

app = FastAPI()


# Lectura de los csv ya transformados
df_games = pd.read_csv('src/games.csv')
df_reviews = pd.read_csv('src/reviews.csv')
df_items = pd.read_csv('src/items.csv')

# Convierte la columna 'genres' en listas utilizando ast.literal_eval()
df_games['genres'] = df_games['genres'].apply(ast.literal_eval)

# Expansion de los generos para las funciones
df_genres = df_games.explode('genres')

# Combina df_items y df_genres en función del id del juego
df_combined = pd.merge(df_items, df_genres, left_on='item_id', right_on='id', how='inner')

# Definición de los endpoints
@app.get("/userdata/")
def userdata(User_id: str):
    # Filtrar datos relevantes para el usuario en los DataFrames
    user_games = df_items[df_items['user_id'] == User_id]
    user_reviews = df_reviews[df_reviews['user_id'] == User_id]

    # Obtener los IDs de los juegos que el usuario ha tenido
    user_game_ids = user_games['item_id']

    # Filtrar los juegos correspondientes en df_games
    user_games_info = df_games[df_games['id'].isin(user_game_ids)]

    # Calcular la cantidad de dinero gastado
    money_spent = float(user_games_info['price'].sum())

    # Calcular el porcentaje de recomendación
    total_reviews = int(len(user_reviews))
    recommended_reviews = float(user_reviews['recommend'].sum())
    recommend_percentage = (recommended_reviews / total_reviews) * 100 if total_reviews > 0 else 0

    # Calcular la cantidad de items
    total_items = int(user_games.items_count.iloc[0])

    return money_spent, recommend_percentage, total_items


@app.get("/countreviews/")
def countreviews(fechaInicial:str, fechaFinal:str):
    df_filtrado = df_reviews[(df_reviews['fecha'] > fechaInicial) & (df_reviews['fecha'] < fechaFinal)]
    cantidad_total = df_filtrado.recommend.count()
    suma_reviews = df_filtrado.recommend.sum()

    porcentaje = (suma_reviews/cantidad_total) * 100 if cantidad_total > 0 else 0

    return f"La cantidad es: {cantidad_total}, el porcentaje de recomendacion de los usuarios es {porcentaje} "

@app.get("/genre/")
def genre(genre_name:str):
	# Agrupa por género y suma las horas jugadas
    genre_hours = df_combined.groupby('genres')['playtime_forever'].sum().reset_index()
	# Ordena el DataFrame por la columna 'PlayTimeForever' en orden descendente
    genre_hours = genre_hours.sort_values(by='playtime_forever', ascending=False)
    genre_hours = genre_hours.reset_index()
    genre_hours.drop(columns=['index'], inplace=True)
    posicion = int(genre_hours[genre_hours['genres'] == genre_name].index[0] + 1)
    return posicion

@app.get("/userforgenre/")
def userforgenre(genero:str):
    df_topgenero = df_combined[df_combined['genres'] == genero]
    df_topgenero = df_topgenero.sort_values(by='playtime_forever', ascending=False)
    df_topgenero = df_topgenero.head(5)
    dicc = dict(zip(df_topgenero['user_id'], df_topgenero['user_url']))
    return dicc

@app.get("/developer/")
def developer(desarrollador:str):
    lista_anios_free = list(df_games[(df_games['developer'] == desarrollador) & (df_games['price'] == 0)].anio.unique())
    dicc = {}
    for i in lista_anios_free:
        total = int(df_games[(df_games['developer'] == desarrollador) & (df_games['anio'] == i)].anio.count())
        suma_free = int(df_games[(df_games['developer'] == desarrollador) & (df_games['anio'] == i) & (df_games['price'] == 0)].anio.count())
        porcentaje = (suma_free/total) * 100
        dicc[str(i)] = round(porcentaje,2)
    return dicc

@app.get("/sentiment_analysis/")
def sentiment_analysis(anio:int):
    df_sentiment = df_reviews[df_reviews['anio'] == anio]
    dicc = {}
    lista_sentimiento = ['Negative', 'Neutral', 'Positive']
    for i in range(0, 3):

        cantidad = int(df_sentiment.sentiment_analysis[df_sentiment['sentiment_analysis'] == i].count())
        dicc[lista_sentimiento[i]] = cantidad
    return dicc
    
# Modelo de recomendacion

#Lectura del csv con el one hot encoding realizado
df_encoded = pd.read_parquet('src/encoded.parquet')

#Guardo las columnas a considerar en el modelo
columnas_df = list(df_encoded.drop(columns=['genres', 'title', 'url', 'release_date', 'reviews_url', 'specs', 'id', 'developer', 'anio', 'price', 'early_access']).columns)

@app.get("/recomendacion_juego/")
def recomendacion_juego(id_juego: str):
    # Selecciona solo las columnas numéricas originales relevantes
    columnas_numericas = columnas_df

    # Crea un nuevo DataFrame con las columnas numéricas
    df_numeric = df_encoded[columnas_numericas]

    # Obtén las características del juego de referencia y elimina las columnas innecesarias
    juego_referencia_caracteristicas = df_numeric[df_encoded['id'] == id_juego]

    # Convierte los resultados en un DataFrame para facilitar su manipulación
    similarity_df = pd.DataFrame(columns=df_encoded['id'])

    # Divide el DataFrame en partes (lotes) más pequeñas
    batch_size = 100  # Puedes ajustar el tamaño del lote según tus necesidades

    for start in range(0, len(df_numeric), batch_size):
        end = start + batch_size
        batch = df_numeric[start:end]

        # Calcula la similitud del coseno para el lote actual y concaténalo al resultado
        similarity_scores = cosine_similarity(juego_referencia_caracteristicas, batch)
        batch_similarity_df = pd.DataFrame(similarity_scores, columns=df_numeric.columns)
        similarity_df = pd.concat([similarity_df, batch_similarity_df], axis=1)

    # Ordena los juegos por similitud descendente
    recommendations = similarity_df.iloc[0].sort_values(ascending=False)

    # Ahora, crea un diccionario de mapeo entre los IDs de juego y los nombres de juego
    id_to_name = dict(zip(df_encoded['id'], df_encoded['title']))

    if id_juego in recommendations:
        recommendations = recommendations.drop(id_juego)

    # Crear una lista de resultados
    result_list = []

    # Iterar a través de las recomendaciones y agregarlas a la lista
    for juego_id, score in recommendations[1:6].items():
        juego_nombre = id_to_name.get(juego_id, 'Desconocido')
        result_list.append({"Juego": juego_nombre, "ID": juego_id, "Similitud": score})

    # Retornar la lista de resultados en formato JSON
    return result_list
