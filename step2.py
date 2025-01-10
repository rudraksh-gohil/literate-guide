import json
import random
import re
import os
import signal
import sys
from groq import Groq

STATE_FILE_PATH = "global_state.json"
MAX_Stories = 8
def reset_global_state():
    global global_state
    global_state = {
        "current_file": None,
        "file_paths": {},
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.2-90b-vision-preview",
            "gemma2-9b-it"
        ],
        "last_model_index": 0,
        "Total_Batches": global_state["Total_Batches"],
        "current_model": "llama-3.3-70b-versatile",
        "exhausted_models": [],
        "processed_files": [],  # Clear the list of processed files
    }
    print("Global state reset process initiated.")

if os.path.exists(STATE_FILE_PATH):
    try:
        with open(STATE_FILE_PATH, "r") as state_file:
            global_state = json.load(state_file)
            # Convert 'processed_files' to a set for faster lookup
            # Ensure 'file_paths' exists for the new structure
            if "file_paths" not in global_state:
                global_state["file_paths"] = {}
        print("Global state loaded successfully.")
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading global state: {e}. Reinitializing state.")
        global_state = {
            "current_file": None,
            "file_paths": {},  # Initialize with an empty dictionary for file paths
            "models": [
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "llama-3.2-90b-vision-preview",
                "gemma2-9b-it"
            ],
            "last_model_index": 0,
            "Total_Batches": 0,
            "current_model": None,
            "exhausted_models": [],
            "processed_files": []
        }
else:
    global_state = {
        "current_file": None,
        "file_paths": {},  # Initialize with an empty dictionary for file paths
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.2-90b-vision-preview",
            "gemma2-9b-it"
        ],
        "last_model_index": 0,
        "Total_Batches": 0,
        "current_model": None,
        "exhausted_models": [],
        "processed_files": []
    }
    print("Global state file not found. Initialized with default values.")


global_state["current_model"] = global_state["models"][global_state["last_model_index"]]

client = Groq(api_key="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")

input_file_paths = [
    os.path.join("ProcessedAppData", f)
    for f in os.listdir("ProcessedAppData")
    if os.path.isfile(os.path.join("ProcessedAppData", f)) and f.startswith("org_") and f.endswith(".json")
]
print(input_file_paths)
file_to_domain_map = {
    os.path.basename(f): re.search(r"org_(.*?)_appdata\.json", f).group(1)
    for f in input_file_paths
}
print(file_to_domain_map)
output_folder_path = "LLM_Processed_Files"
MAX_RETRIES = 3
Counter = 0

total_stories_generated = 0
total_stories_parsed = 0

interrupted = False
output_file = None

if not os.path.exists(output_folder_path):
    os.makedirs(output_folder_path)


def save_state():
    global global_state
    state_to_save = global_state.copy()
    state_to_save["processed_files"] = list(global_state["processed_files"])  # Convert set to list for serialization
    with open(STATE_FILE_PATH, "w") as state_file:
        json.dump(state_to_save, state_file, indent=4)



def cleanup_output_file():
    """
    Ensures that the output file is properly closed and formatted.
    """
    global output_file
    if output_file and not output_file.closed:
        try:

            output_file.seek(0, os.SEEK_END)
            if output_file.tell() > 0:
                output_file.write("\n]")
                save_state()
            output_file.close()
            print(f"Output file properly closed: {output_file.name}")
        except Exception as e:
            print(f"Error during file cleanup: {e}")
        finally:
            output_file = None


def switch_model():
    global global_state
    global_state["last_model_index"] = (global_state["last_model_index"] + 1) % len(global_state["models"])
    global_state["current_model"] = global_state["models"][global_state["last_model_index"]]
    print(f"Switched to model: {global_state['current_model']}")



def signal_handler(sig, frame):
    """
    Handle keyboard interrupts (Ctrl+C) and other signals.
    """
    global interrupted
    print("\nInterrupt received. Cleaning up...")
    interrupted = True
    cleanup_output_file()
    save_state()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def parse_user_story_output(user_story, path_metadata, available_apps):
    global total_stories_parsed
    try:

        json_block_pattern = r"```json\s*(.*?)\s*```"
        json_match = re.search(json_block_pattern, user_story, re.DOTALL)

        if json_match:
            json_data = json_match.group(1).strip()

            try:
                parsed_json = json.loads(json_data)
            except json.JSONDecodeError as e:
                print(f"Malformed JSON in ```json...``` block. Error: {e}")
                print(f"Faulty JSON Block:\n{json_data}")
                return {"error": f"Malformed JSON in ```json...``` block", "faulty_json": json_data}

        elif "<jsonstart>" in user_story and "<jsonend>" in user_story:
            json_data_pattern = r"<jsonstart>(.*?)<jsonend>"
            json_match = re.search(json_data_pattern, user_story, re.DOTALL)

            if json_match:
                json_data = json_match.group(1).strip()

                try:
                    parsed_json = json.loads(json_data)
                except json.JSONDecodeError as e:
                    print(f"Malformed JSON between <jsonstart> and <jsonend>. Error: {e}")
                    print(f"Faulty JSON Block:\n{json_data}")
                    return {"error": f"Malformed JSON in <jsonstart>...<jsonend>", "faulty_json": json_data}

        elif user_story.strip().startswith("{") and user_story.strip().endswith("}"):

            try:
                parsed_json = json.loads(user_story.strip())
            except json.JSONDecodeError as e:
                print(f"Malformed bare JSON. Error: {e}")
                print(f"Faulty JSON Block:\n{user_story.strip()}")
                return {"error": "Malformed bare JSON", "faulty_json": user_story.strip()}

        else:
            print(f"No valid JSON block found. Raw content:\n{user_story.strip()}")
            return {"error": "No valid JSON block found", "faulty_json": user_story.strip()}

        if "User Stories" in parsed_json:
            for user_story in parsed_json["User Stories"]:
                user_story["App Names"] = available_apps

                common_bugs = user_story.get("Common Bugs", {})
                common_bugs.setdefault("Functional", [])
                common_bugs.setdefault("Non-Functional", [])

            total_stories_parsed += len(parsed_json["User Stories"])

        return {"metadata": path_metadata, "data": parsed_json}

    except Exception as e:
        print(f"Error parsing user story output: {e}")
        return {"error": str(e), "faulty_json": user_story}


def generate_combinations(features, max_combinations=10):
    variations = []
    while len(variations) < max_combinations:
        num_features = min(random.randint(1, 3), len(features))
        selected_features = random.sample(features, num_features)

        feature_details = {
            "Features": [feature["Feature"] for feature in selected_features],
            "Available Apps": {},
            "Acceptance Criteria": set(),
            "Common Bugs": set(),
        }

        for feature in selected_features:
            for region, app_list in feature.get("apps", {}).items():
                feature_details["Available Apps"].setdefault(region, set()).update(app_list)

            feature_details["Acceptance Criteria"].update(
                feature.get("acceptance_criteria", {}).get("mobile", [])
            )
            feature_details["Common Bugs"].update(
                feature.get("common_bugs", {}).get("mobile", [])
            )

        feature_details["Available Apps"] = {k: list(v) for k, v in feature_details["Available Apps"].items()}
        feature_details["Acceptance Criteria"] = list(feature_details["Acceptance Criteria"])
        feature_details["Common Bugs"] = list(feature_details["Common Bugs"])

        variations.append(feature_details)

    return variations


def traverse_hierarchy(data, path=[]):
    solutions = []
    for key, value in data.items():
        current_path = path + [key]
        if isinstance(value, dict):
            solutions += traverse_hierarchy(value, current_path)
        elif isinstance(value, list):
            solutions.append({
                "Path": current_path[:-1],
                "Requirement Type": current_path[-1],
                "Features": value
            })
    return solutions


def generate_user_story_for_all_qualities(feature_details, domain, subdomain, platform, software_type,
                                          requirement_type):
    example_json = """
        ```json
            {
                "Feature Name": ["feature1", "feature2"],
                "User Stories": [
                    {
                        "Quality": "High",
                        "User Story": "As a user, I want feature1 and feature2 so that I can achieve specific goals related to both features.",
                        "Acceptance Criteria": ["Acceptance criterion 1", "Acceptance criterion 2"],
                        "Common Bugs": {
                            "Functional": ["Functional Bug 1", "Functional Bug 2"],
                            "Non-Functional": ["NFR Bug 1", "NFR Bug 2"]
                        }
                    },
                    {
                        "Quality": "Average",
                        "User Story": "As a user, I want feature1 and feature2 for improved functionality.",
                        "Acceptance Criteria": ["Acceptance criterion 1", "Acceptance criterion 2"],
                        "Common Bugs": {
                            "Functional": ["Functional Bug 1", "Functional Bug 2"],
                            "Non-Functional": ["NFR Bug 1", "NFR Bug 2"]
                        }
                    },
                    {
                        "Quality": "Low",
                        "User Story": "As a user, I want feature1.",
                        "Acceptance Criteria": ["Acceptance criterion 1"],
                        "Common Bugs": {
                            "Functional": ["Functional Bug 1", "Functional Bug 2"],
                            "Non-Functional": ["NFR Bug 1", "NFR Bug 2"]
                        }
                    }
                ]
            }
        ```
        """

    prompt = f"""
        Context Information
            - Given the Domain: {domain}
            - Given the Subdomain: {subdomain}
            - Given the Platform Name: {platform}
            - Given the Software Type: {software_type}
            - Given the Requirement Type: {requirement_type}

        Features Overview
            - The following features are included in this variation: {', '.join(feature_details['Features'])}

        Acceptance Criteria
            - The features are expected to meet the following acceptance criteria: {', '.join(feature_details['Acceptance Criteria'])}

        Common Bugs
            - Known issues: {', '.join(feature_details['Common Bugs'])}
            - Generate additional bugs related to the provided features.
            - Categorize all bugs under **functional** and **non-functional** categories for better clarity.

        Purpose of Generating User Story:
            - Generate synthetic user stories to train ML models for classifying user-inputted stories under various attributes (e.g., subdomain, platform, requirement type).
            - Simulate real-world variability by incorporating ambiguities, edge cases, and constraints.

        Task:
            Please generate **one base user story** based on the context and features described above. Then, modify this story based on the three different quality levels (high, average, low). Ensure the modifications reflect the level of detail and complexity typical for each quality level.
            The output must **only** be in JSON format, and you must adhere to the provided notes.
            All user stories must relate to all given parameters such as domain, subdomain, platform, software type, and others.

        Notes:
            - The **base user story** should be complete and cover the essential features, user needs, and goals, while also including some level of ambiguity or complexity.
            - **High-Quality User Story**: Expand the base story with richer details, including multiple aspects of feature interactions, constraints, challenges, and expected system behaviors. This version should have detailed acceptance criteria and categorized common bugs.
            - **Average-Quality User Story**: Simplify the story slightly, focusing on key aspects and user goals but leaving out some complexity and edge cases. Acceptance criteria and bugs should be **properly organized** and moderately detailed.
            - **Low-Quality User Story**: Make the story more minimalistic, focusing only on the essential user goals. This version should lack detailed context, and the story may be vague or incomplete. The acceptance criteria and bugs should be **brief** and not fully fleshed out.

            All user stories should:
            - Be related to all given parameters such as domain, subdomain, platform, software type, and features.
            - Avoid explicitly mentioning the software type (e.g., Frontend, Backend, etc.) as well as the platform (e.g., Mobile, Web), though it will influence the story generation.
            - Include **ambiguities**, **edge cases**, and **real-world variability**.

        Output Format:
            - Strictly follow the format below for user story generation and make you start it properly as per described in below format:
            {example_json}

            Additional Enhancements for Realism:
                - Simulate dynamic user personas with diverse contexts (e.g., novice, expert, accessibility-focused users).
                - Simulate natural language variations (e.g., informal expressions, or domain-specific jargon).

            Ensure the output is strictly in JSON format with no explanation or other text.
    """

    return prompt


def handle_rate_limits(error_message=None):
    """Handle model switching when rate limit is reached."""
    global global_state

    if error_message:

        if "429" in str(error_message):
            print(f"Rate limit reached for {global_state['current_model']}. Switching model.")
            global_state["exhausted_models"].append(global_state["current_model"])
            switch_model()


def all_models_exhausted():
    """Check if all models have exhausted their rate limits."""
    return len(global_state["exhausted_models"]) == len(global_state["models"])


# Process files in batches until all are processed
# Calculate number of input files and allocate stories equally
num_files = len(input_file_paths)
stories_per_file = MAX_Stories // num_files  # Integer division of stories per file
def remove_trailing_bracket(output_file_path):
    try:
        # Check if the file exists and is not empty
        if os.path.exists(output_file_path) and os.stat(output_file_path).st_size > 0:
            with open(output_file_path, "r+") as file:
                data = file.read()
                # Check if the file ends with a closing bracket ']'
                if data.endswith("]"):
                    # Remove the trailing bracket and overwrite the file
                    file.seek(0)  # Move to the start of the file
                    file.write(data[:-1])  # Remove the last character (']')
                    file.truncate()  # Ensure file size is adjusted
                    file.write(',\n')  # Optionally add a comma and newline before the closing bracket
    except FileNotFoundError:
        print(f"File not found, skipping: {output_file_path}")
    except Exception as e:
        print(f"Error processing file {output_file_path}: {e}")



def cleaner (output_folder_path):
    # List all files in the output folder
    for file_name in os.listdir(output_folder_path):
        output_file_path = os.path.join(output_folder_path, file_name)

        # Proceed only if it's a file
        if os.path.isfile(output_file_path):
            with open(output_file_path, "w") as file:
                file.truncate(0)  # Clears the contents of the file
                print(f"Cleaned {file_name}")


def ensure_closing_bracket(output_folder_path):
    # List all files in the output folder
    for file_name in os.listdir(output_folder_path):
        output_file_path = os.path.join(output_folder_path, file_name)

        # Proceed only if it's a file and not empty
        if os.path.isfile(output_file_path) and os.stat(output_file_path).st_size > 0:
            with open(output_file_path, "r+") as file:
                data = file.read()

                # Check if the file ends with a closing bracket ']'
                if not data.endswith(']'):
                    print(f"Adding closing bracket to {file_name}")
                    file.seek(0, os.SEEK_END)  # Move to the end of the file
                    file.write("\n]")  # Add the closing bracket
cleaner(output_folder_path)
while True:
    # Check if all files are fully processed
    fully_processed_files = set(global_state["processed_files"])
    remaining_files = [
        f for f in input_file_paths if os.path.basename(f) not in fully_processed_files
    ]

    if not remaining_files:
        print("All files fully processed successfully!")
        break  # Exit loop when all files are processed

    # Process remaining files
    # Track the processed paths for each file
    processed_paths = {}

    for json_file_path in remaining_files:
        file_name = os.path.basename(json_file_path)
        try:
            domain = file_to_domain_map[file_name]
            global_state["current_file"] = file_name

            # Get the last processed path for the file from global_state
            current_path = global_state["file_paths"].get(file_name, [])

            with open(json_file_path, "r") as file:
                data = json.load(file)

            all_groups = traverse_hierarchy(data)

            start_processing_from = current_path == []
            output_file_path = os.path.join(output_folder_path, f"LLM_{file_name}")
            first_entry = True  # Track first JSON entry for formatting
            remove_trailing_bracket(output_file_path)
            # Open output file and write opening bracket
            with open(output_file_path, "a") as output_file:  # Append mode
                if os.stat(output_file_path).st_size == 0:  # If file is empty, write array start
                    output_file.write("[\n")

                total_stories_generated_for_file = 0  # Track stories generated for this file
                unprocessed_paths_exist = False  # Track if there are unprocessed paths

                # Initialize path processing state for the current file if not already
                if file_name not in processed_paths:
                    processed_paths[file_name] = set()

                for group in all_groups:
                    if group["Path"] == current_path:
                        start_processing_from = True

                    if start_processing_from:
                        features = group["Features"]
                        requirement_type = group["Requirement Type"]
                        path = group["Path"]
                        variations = generate_combinations(features, max_combinations=3)

                        subdomain, platform, software_type = (
                                path + ["N/A"] * (3 - len(path))  # Handle missing path elements
                        )
                        path_metadata = {
                            "Subdomain": subdomain,
                            "Platform": platform,
                            "Software Type": software_type,
                            "Requirement Type": requirement_type,
                        }

                        for variation in variations:
                            # Stop processing if the limit is reached
                            if total_stories_generated_for_file >= stories_per_file:
                                unprocessed_paths_exist = True
                                break  # Exit the variations loop

                            # Stop processing if global story limit is reached
                            if total_stories_generated >= MAX_Stories:
                                print("Global story limit reached. Terminating execution.")
                                save_state()
                                sys.exit(0)  # Exit the script

                            prompt = generate_user_story_for_all_qualities(
                                variation, domain, subdomain, platform, software_type, requirement_type
                            )

                            retries = 0
                            while retries < MAX_RETRIES:
                                try:
                                    if all_models_exhausted():
                                        print("All models have exhausted their rate limits.")
                                        save_state()
                                        sys.exit(1)

                                    completion = client.chat.completions.create(
                                        model=global_state["current_model"],
                                        messages=[{"role": "user", "content": prompt}],
                                        temperature=1,
                                        max_tokens=1200,
                                        top_p=1,
                                        stream=True,
                                    )

                                    user_story_raw = "".join(
                                        chunk.choices[0].delta.content or "" for chunk in completion
                                    )
                                    total_stories_generated += 1
                                    total_stories_generated_for_file += 1
                                    print(
                                        f"Generation Successful: {subdomain} -> {platform} -> {software_type} -> {requirement_type}"
                                    )

                                    parsed_data = parse_user_story_output(
                                        user_story_raw, path_metadata, variation["Available Apps"]
                                    )

                                    if parsed_data:
                                        if not first_entry:
                                            output_file.write(",\n")
                                        json.dump(parsed_data, output_file, indent=2)
                                        first_entry = False

                                    total_stories_parsed += 1

                                    # Update the path after every generation
                                    global_state["file_paths"][file_name] = path

                                    # Mark the current path as processed
                                    processed_paths[file_name].add(tuple(path))

                                    break

                                except Exception as e:
                                    if "429" in str(e):
                                        print(e)
                                        handle_rate_limits(str(e))
                                        retries = 0
                                    else:
                                        print(f"Error on attempt {retries + 1}/{MAX_RETRIES}: {e}")
                                        retries += 1

                                    if retries == MAX_RETRIES:
                                        print("Max retries reached. Skipping this variation.")

                        if total_stories_generated_for_file >= stories_per_file:
                            break  # Exit the group loop if limit is reached

                        # Update the current path for this file
                        global_state["file_paths"][file_name] = group["Path"]

                # If no unprocessed paths exist, mark file as fully processed
                if not unprocessed_paths_exist and processed_paths[file_name] == set(
                        tuple(g["Path"]) for g in all_groups):
                    global_state["processed_files"].append(file_name)

                # Ensure closing bracket is written to the output file
                output_file.write("\n]")

                print(f"Data successfully written to {output_file_path}")

                # Exit if global story limit is reached
                if total_stories_generated >= MAX_Stories:
                    print("Global story limit reached. Terminating execution.")
                    save_state()
                    sys.exit(0)
        except Exception as e:
            print(f"Error processing JSON file {json_file_path}: {e}")
        finally:
            save_state()
            ensure_closing_bracket(output_folder_path)

if len(global_state["processed_files"]) == len(input_file_paths):
    reset_global_state()
    save_state()