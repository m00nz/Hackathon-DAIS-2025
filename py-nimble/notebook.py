""
Run this as a notebook.


""

import requests

dbutils.secrets.list(scope="nimble")

NIMBLE_TOKEN = dbutils.secrets.get(scope="nimble", key="bearer")

# print(NIMBLE_TOKEN)

# https://docs.nimbleway.com/nimble-sdk/web-api/vertical-endpoints/maps-api/collecting-reviews#using-a-place_id-or-data_id
def get_reviews_from_nimble(place_id: str):
    global NIMBLE_TOKEN

    url = 'https://api.webit.live/api/v1/realtime/serp'
    headers = {
        'Authorization': f'Bearer {NIMBLE_TOKEN}',
        'Content-Type': 'application/json'
    }
    data = {
        "search_engine": "google_maps_reviews",
        "place_id": f"{place_id}"
    }

    response = requests.post(url, headers=headers, json=data)
    return response.json()


# get data by query

def get_places_by_city(city: str):

    # Define your SQL query
    sql_query = """
    SELECT
      address,
      name,
      category,
      place_id
    FROM
      polar_dais_hackathon_2025.bright_initiative.google_maps_businesses
    WHERE
      address ILIKE '%city%'
    LIMIT 2

    """

    # Execute the SQL query
    df = spark.sql(sql_query)

    return df 


df = get_places_by_city('San Francisco')
df.count()


for row in df.collect():
  print(row['place_id'])

  place_id = row['place_id']

  print('calling nimble api for place_id {place)id}')

  review = get_reviews_from_nimble(place_id)

  print(review)





