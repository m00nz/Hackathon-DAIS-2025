from databricks.sdk import WorkspaceClient

client = WorkspaceClient()
# from unitycatalog.ai.core.databricks import DatabricksFunctionClient
# client = DatabricksFunctionClient()

def get_wellness_centers(city:str) -> str:
    """
    Returns a DataFrame containing the top 10 wellness centers in the given city.
    """
    query = f"""
      WITH gmb AS (
    SELECT name
      , address
      , split_part(address, ',',2) as city
      , split_part(split_part(address, ',', -1), ' ',2) as state_id
      , split_part(split_part(address, ',', -1), ' ',3) as zip_code
      , category
      , lat
      , lon
      , main_image
      , open_hours
      , open_hours_updated
      , open_website
      , phone_number
      , place_id
      , price_range
      , rating
      , reviews
      , reviews_count
      , services_provided
      , url
    FROM polar_dais_hackathon_2025.bright_initiative.google_maps_businesses
    WHERE category RLIKE 'Health|Wellness|Psychotherapist|Speech pathologist|Physical therapy clinic|Sports medicine clinic|Diagnostic center|Eye care center|Ophthalmology clinic|Medical clinic|Mental health clinic|Crisis center|Addiction treatment center|Massage spa|Massage therapist|Chiropractor|Acupuncturist|Reiki therapist|Holistic medicine practitioner|Nutritionist|Yoga studio|Meditation center|Pilates studio|Indoor cycling|Personal trainer|Fitness center|Physical fitness program|Psychiatrist|Psychologist|Counselor|Counseling service|Community center|Support group|Recreation center|Child psychologist'
  )
  SELECT * FROM gmb
  WHERE city ILIKE '%{city}%'
  AND reviews_count > 0
  LIMIT 10
  """
    return spark.sql(query).toJSON()  

function_info = client.functions.create(
  name="get_wellness_centers",
  catalog="polar_dais",
  schema="polar",
  replace=True
)