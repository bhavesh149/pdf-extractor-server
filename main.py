from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import aiofiles, json, random, re, os, fitz
from openai import OpenAI

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#################################   Enter API Key Here  ################################################################
api_key = 'sk-proj-BoaMiHCnSbCeFN3gGpHiT3BlbkFJhOpPrblzIxCwNGdHdp6y' ###
########################################################################################################################

client = OpenAI(api_key=api_key)

async def wait_on_run(run, thread):
    while run.status == "queued" or run.status == "in_progress":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
    return run

async def submit_message(assistant_id, thread, user_message):
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=user_message
    )
    return client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
    )

async def create_thread_and_run(user_input: str, assistant_id_: str):
    thread = client.beta.threads.create()
    run = await submit_message(assistant_id_, thread, user_input)
    return thread, run

async def get_response(thread):
    return client.beta.threads.messages.list(thread_id=thread.id)

def pretty_print(messages):
    for m in messages:
        return f"{m.content[0].text.value}"

async def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        text += page.get_text("text")
    filename = os.path.basename(pdf_path)    # Extracting the filename from the path
    return filename, text

async def save_to_json(data, filename):
    async with aiofiles.open(filename, 'w', encoding='utf-8') as file:
        await file.write(json.dumps(data, ensure_ascii=False, indent=4))

async def read_json(filename):
    async with aiofiles.open(filename, 'r', encoding='utf-8') as file:
        return json.loads(await file.read())

def get_random_questions_and_answers(json_data, num_questions=3):
    questions = json_data['qu']
    answers = json_data['ans']
    
    indices = list(range(1, len(questions) + 1))
    random.shuffle(indices)
    selected_indices = indices[:num_questions]
    
    res2 = {
        "qu": {questions[str(i)] for i in selected_indices},
        "ans": {answers[str(i)] for i in selected_indices}
    }
    return res2

############################    Assistant   ############################################################################

@app.get('/')
async def myFun():
    return {"Hey from fastapi!"}

@app.post('/ai')
async def assit(input_: str, assistant_id_: str):
    if any(input_.strip().lower().startswith(word) for word in ["hi", "hey", "hello","?"]):
        
        if input_.lower() == "?":
            return {"ans": f"Hello! I am an AI chat assistant here to provide information and assistance. How can I help you today?"}
        return {"ans": f"{ input_.strip().split()[0]}! I am an AI chat assistant here to provide information and assistance. How can I help you today?"}

    if any(word in input_.lower() for word in ["image", "images", "photos", "pictures", "pic", "looks", "look"]):
        return "I can only answer to question related to Text."
        input_ += " only give me all possible image links as [name](links), don't include logos or social media platforms."
        thread1, run1 = await create_thread_and_run(input_, assistant_id_)
        run1 = await wait_on_run(run1, thread1)
        res = pretty_print(await get_response(thread1))

        image_links = re.findall(r'\((.*?)\)', res)
        if any((link.endswith(('.jpg', '.jpeg')) and link.startswith("//")) for link in image_links):
            jpg_links = [link for link in image_links if (link.endswith(('.jpg', '.jpeg')) and link.startswith("//"))]
            jpg_links = ["https://" + link[2:] if link.startswith("//") else link for link in jpg_links]
            res = jpg_links
        else:
            res = image_links
        return {"ans": res}
    else:
        thread1, run1 = await create_thread_and_run(input_, assistant_id_)
        run1 = await wait_on_run(run1, thread1)
        res = pretty_print(await get_response(thread1))
        try:
            res_dict = json.loads(res)
        except json.JSONDecodeError:
            res_dict = res
        return {"ans": res_dict}
    
##############################   PDF Scraper  ###########################################################################
@app.post('/pdf')
async def pdf_information(file: UploadFile = File(...)):
    try:
        temp_file_path = f"temp_{file.filename}"
        async with aiofiles.open(temp_file_path, 'wb') as out_file:
            while content := await file.read(1024):  # Read the file in chunks
                await out_file.write(content)

        # Extract text from the temporary PDF file
        filename_, extracted_text = await extract_text_from_pdf(temp_file_path)
        _='''You are a chat assistant for Tata Capital, a leading financial services provider in India, offering a wide range of loan products to cater to various financial needs. Your primary focus is to assist users with everything related to Tata Capital’s loan offerings. You only guide and give answers related to this products. Below are the details. only question and answer given by a human assistant working in call center . Managerial post not engineering. Do not give code.'''
        _+=extracted_text
        assistant = client.beta.assistants.create(
            name="CustomGPT",
            instructions= _,
            model="gpt-3.5-turbo",
        )

        thread = client.beta.threads.create()
        message = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Hi",
        )

        run = client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id,
        )
        run = await wait_on_run(run, thread)

        messages = await get_response(thread)
        assistant_id = ""
        for message in messages:
            if message.role == 'assistant':
                assistant_id = message.assistant_id
        
        # Store the assistant ID and filename in a JSON file
        assistant_data = {}
        if os.path.exists("assistant_data.json"):
            async with aiofiles.open("assistant_data.json", 'r', encoding='utf-8') as file:
                assistant_data = json.loads(await file.read())
        
        assistant_data[filename_] = assistant_id
        await save_to_json(assistant_data, "assistant_data.json")

        os.remove(temp_file_path)
        return {"success": True, "id": assistant_id, "filename": filename_}
    
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get('/pdf_data')
async def get_pdf_data():
    try:
        if os.path.exists("assistant_data.json"):
            async with aiofiles.open("assistant_data.json", 'r', encoding='utf-8') as file:
                assistant_data = json.loads(await file.read())
                return assistant_data
        else:
            return {"error": "assistant_data.json not found."}
    except Exception as e:
        return {"error": str(e)}

#########################################################################################################################

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8000, workers=4, reload=True)
