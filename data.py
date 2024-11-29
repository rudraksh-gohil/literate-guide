import random
from urllib.parse import quote_plus
from groq import Groq
import certifi
from pymongo import MongoClient
from datetime import datetime
import time

username = "rudu"
password = "sample@12"

encoded_username = quote_plus(username)
encoded_password = quote_plus(password)

uri = f"mongodb+srv://{encoded_username}:{encoded_password}@cluster0.rsk4r.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(uri, tlsCAFile=certifi.where())

db = client["Sy_userstories_db"]
collection = db["stories"]
collection.create_index("UserStory", unique=True)

api_key = ""
if not api_key:
    print("API Key is missing! Please set the GROQ_API_KEY environment variable.")
    exit()
client_groq = Groq(api_key=api_key)

user_message_template = """ Generate a user story for a system or feature with the following specifications. Each user story must adhere to these rules and output fields exactly:

1. Region: Specify the geographical or operational region where the system or feature applies (e.g., 'North America,' 'Europe,' 'Asia-Pacific'). The feature should adapt based on regional requirements and context.  

2. Quality: Randomly assign one of the following quality levels with equal probability:
    - "high": Comprehensive and contextually rich, including detailed descriptions.
    - "average": Moderately detailed, striking a balance between thoroughness and brevity.
    - "low": Minimal detail, focusing on essential information or leaving some details and if the format of user story is distributed for low quality user story is okay.  
    - Selected Quality = {quality}, should affect the overall quality of the output  

3. Feature: Clearly define the system's main functionality, tailored to the region (e.g., 'Data analysis dashboard,' 'Real-time notifications,' 'User authentication').  

4. Domain: Identify the broader industry where this feature or system will be applied (example 'Healthcare,' 'E-commerce,' 'Finance').you could other domain also not these 3  . the variety of domain should be huge.  

5. Sub_domain: Specify the niche or targeted segment within the domain (e.g., 'Patient data management,' 'Fraud detection,' 'Inventory management').  

6. Platform: Specify the type of device the user will use to access and utilize the platform's features (e.g., 'Mobile App', 'Desktop App'). Ensure that the features are tailored to and relevant for the selected platform.
### User Story Format
Write the user story in this format:  
"As a [type of user], I want [goal] so that [reason]." Exception for low quality of user stories. (If Selected).  

Output Format: Return the user story as a valid json formatted data and nothing else, following this exact structure:  
{{"region": "string","quality": "{quality}","feature": "string","domain": "string","sub_domain": "string","platform":"string","UserStory": "As a [type of user], I want [goal] so that [reason]"}}
Other than the valid json formatted data and nothing else even the header should not be included in output, no other type of information should be shown in output.
"""

models = ["gemma2-9b-it", "llama-3.1-70b-versatile"]
max_requests_per_minute = 28
requests_made = {"gemma2-9b-it": 0, "llama-3.1-70b-versatile": 0}
last_reset_time = time.time()

max_retries = 3
retry_delay = 3


def assign_quality_dynamically(total_requests, high_percentage=0.3, average_percentage=0.5, low_percentage=0.2):
    num_high = int(total_requests * high_percentage)
    num_average = int(total_requests * average_percentage)
    num_low = total_requests - num_high - num_average

    qualities = ['high'] * num_high + ['average'] * num_average + ['low'] * num_low
    random.shuffle(qualities)
    return qualities


def wait_for_rate_limit(model):
    global last_reset_time
    current_time = time.time()
    elapsed_time = current_time - last_reset_time

    if elapsed_time < 60 and requests_made[model] >= max_requests_per_minute:
        wait_time = 60 - elapsed_time
        print(f"Rate limit reached for {model}. Waiting for {wait_time:.2f} seconds...")
        time.sleep(wait_time)
        last_reset_time = time.time()
        requests_made[model] = 0


total_requests_per_model = 28
qualities = assign_quality_dynamically(total_requests_per_model)

for model in models:
    for i in range(total_requests_per_model):
        quality = qualities[i]
        user_message = user_message_template.format(quality=quality)

        attempts = 0
        while attempts < max_retries:
            try:
                wait_for_rate_limit(model)

                completion = client_groq.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": user_message}],
                    temperature=1,
                    max_tokens=1024,
                    top_p=1
                )
                response = completion.choices[0].message.content.strip()

                if response.startswith("{") and response.endswith("}"):
                    response_dict = eval(response)
                else:
                    print(f"Unexpected response format: {response}")
                    continue


                timestamp = datetime.utcnow()
                response_dict = {"timestamp": timestamp, "model": model, **response_dict}

                
                existing_story = collection.find_one({"UserStory": response_dict["UserStory"]})
                if existing_story:
                    print(f"Duplicate user story found: {response_dict['UserStory']}. Skipping insertion.")
                    break
                else:
                    collection.insert_one(response_dict)
                    print("Saved to MongoDB successfully.")
                    requests_made[model] += 1
                    break

            except Exception as e:
                attempts += 1
                print(f"Error occurred while generating response with {model}: {e}")
                if attempts < max_retries:
                    print(f"Retrying... ({attempts}/{max_retries})")
                    time.sleep(retry_delay)
                else:
                    print("Max retries reached, skipping to next attempt.")
