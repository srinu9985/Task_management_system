from fastapi import FastAPI, Request, Form, HTTPException, Depends, Body
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse, JSONResponse
from pymongo import MongoClient
from fastapi.middleware.cors import CORSMiddleware
import re
from bson import ObjectId
from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64
import google.generativeai as genai
from pydantic import BaseModel

app = FastAPI()
genai.configure(api_key="AIzaSyCgBsRq7nR_z4CweXqu_ebcay_BqZwIdkI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
client = MongoClient('mongodb://localhost:27017/')
db = client['homepage']
users_collection = db['users']
tasks_collection = db['tasks']

class TaskRequest(BaseModel):
    short_task_name: str

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register")
async def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

def is_valid_email(email):
    pattern = r'^[\w\.-]+@gmail\.com$'
    return re.match(pattern, email) is not None

def create_user(username, email, password, role):
    user = {
        "_id": str(ObjectId()),
        "username": username,
        "email": email,
        "password": password,
        "role": role
    }
    users_collection.insert_one(user)
    return user["_id"]

def check_login(email, password):
    user = users_collection.find_one({"email": email, "password": password})
    return user

@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    user = check_login(email, password)
    if user:
        return JSONResponse(content={"message": "Login successful", "role": user["role"], "username": user["username"],"email": user["email"]})
    else:
        # return JSONResponse(content={"message": "Login failed"}, status_code=401)
        existing_user = users_collection.find_one({"email": email})
        if existing_user:
            # error_message = "Incorrect password. Please try again."
            return JSONResponse(content={"message": "Incorrect password"})
        else:
            # error_message = "Invalid credentials. Please sign up first!"
            return JSONResponse(content={"message": "Invalid credentials"})

        # return templates.TemplateResponse("login.html", {"request": request, "error": error_message})

@app.get("/logout")
async def logout(request: Request):
    return RedirectResponse(url="/")

@app.post("/register")
def post_register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    repassword: str = Form(...),
    role: str = Form(...)
):
    if password != repassword:
        return JSONResponse(content={"message": "Passwords do not match"}, status_code=400)
    
    if not is_valid_email(email):
        return JSONResponse(content={"message": "Invalid email format"}, status_code=400)
    
    existing_user = users_collection.find_one({"$or": [{"username": username}, {"email": email}]})
    if existing_user:
        if existing_user["role"] == role:
            return JSONResponse(content={"message": "Username or email already taken for this role"}, status_code=400)
        else:
            # Allow registration with a different role
            user_id = create_user(username, email, password, role)
            return JSONResponse(content={"message": f"User registered as {role}", "user_id": user_id})
    if role not in ["manager", "user"]:
        return JSONResponse(content={"message": "Invalid role"}, status_code=400)
    
    user_id = create_user(username, email, password, role)
    return JSONResponse(content={"message": "Registration successful", "user_id": user_id})

@app.get("/admindashboard")
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admindashboard.html", {"request": request})

@app.get("/userdashboard")
async def user_dashboard(request: Request):
    return templates.TemplateResponse("userdashboard.html", {"request": request})

@app.post("/create_task")
async def create_task(
    title: str = Form(...),
    description: str = Form(...),
    priority: str = Form(...),
    status: str = Form(...),
    due_date: str = Form(...),
    assigned_to: str = Form(...),
    assignedManager: str = Form(...)
):
    print(f"Received task data: title={title}, description={description}, priority={priority}, status={status}, due_date={due_date}, assigned_to={assigned_to},assignedManager={assignedManager}")
    
    assigned_to_list = [user.strip() for user in assigned_to.split(',')]
    task = {
        "_id": str(ObjectId()),
        "title": title,
        "description": description,
        "priority": priority,
        "status": status,
        "dueDate": due_date,
        "assignedTo": assigned_to_list,
        "assignedManager":assignedManager,
        "created_at": datetime.now().isoformat()
    }
    tasks_collection.insert_one(task)
    return JSONResponse(content={"message": "Task created successfully", "task_id": task["_id"]})

@app.get("/get_tasks")
async def get_tasks(
    search: str = None,
    priority: str = None,
    status: str = None,
    due_date: str = None,
    assigned_to: str = None,
    assignedManager: str = None
):
    print("assigned_to",assigned_to)
    print("assigned_to",assignedManager)
    query = {}
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}}
        ]
    if priority:
        query["priority"] = priority
    if status:
        query["status"] = status
    if due_date:
        query["dueDate"] = due_date
    if assigned_to:
        query["assignedTo"] = assigned_to
    if assignedManager:
        # Fetch tasks where the manager_email is in the assignedTo list
        query["assignedManager"] = assignedManager
    
    tasks = list(tasks_collection.find(query))
    print("tasks",tasks)
    for task in tasks:
        task["_id"] = str(task["_id"])
    return JSONResponse(content=tasks)


@app.put("/update_task/{task_id}")
async def update_task(task_id: str, task_data: dict = Body(...)):
    print("task_id:", task_id)
    
    # Prepare the query based on _id type
    query = {"$or": [{"_id": task_id}]}
    if ObjectId.is_valid(task_id):
        query["$or"].append({"_id": ObjectId(task_id)})

    print("query",query)
    updated_task = {
        "title": task_data.get("title"),
        "description": task_data.get("description"),
        "priority": task_data.get("priority"),
        "status": task_data.get("status"),
        "dueDate": task_data.get("dueDate"),
        "assignedTo": task_data.get("assignedTo"),
    }

    result = tasks_collection.update_one(query, {"$set": updated_task})

    if result.modified_count > 0:
        return JSONResponse(content={"message": "Task updated successfully"})
    else:
        return JSONResponse(content={"message": "Task not found"}, status_code=404)

@app.delete("/delete_task/{task_id}")
async def delete_task(task_id: str):
    result = tasks_collection.delete_one({"_id": task_id})
    if result.deleted_count > 0:
        return JSONResponse(content={"message": "Task deleted successfully"})
    else:
        return JSONResponse(content={"message": "Task not found"}, status_code=404)

@app.get("/get_users")
async def get_users():
    users = users_collection.find({"role": "user"}, {"_id": 0, "email": 1})  # Fetch only emails
    user_list = [user["email"] for user in users]
    return {"users": user_list}


# @app.put("/update_task_status/{task_id}")
# async def update_task_status(task_id: str, status: str):
#     result = tasks_collection.update_one(
#         {"_id": ObjectId(task_id)},
#         {"$set": {"status": status}}
#     )
#     if result.modified_count > 0:
#         # Notify admin (you can implement this part based on your notification system)
#         return JSONResponse(content={"message": "Task status updated successfully"})
#     else:
#         return JSONResponse(content={"message": "Task not found"}, status_code=404)


#Report generation
@app.post("/generate_report")
async def generate_text_report(request: Request):
    data = await request.json()
    manager_email = data.get("managerEmail")  # Extract manager email from request

    # Fetch tasks assigned by the manager
    in_progress_tasks = tasks_collection.find({"status": "In Progress", "assignedManager": manager_email})
    completed_tasks = tasks_collection.find({"status": "Completed", "assignedManager": manager_email})

    print("tasks completed vs progress", completed_tasks,in_progress_tasks)
    # Build the report
    report = []
    report.append("Task Report: In Progress vs Completed")
    report.append("=" * 40)
    
    # Add in-progress tasks
    report.append("\nIn Progress Tasks:")
    for task in in_progress_tasks:
        report.append(f"- Title: {task['title']}")
        report.append(f"  Assigned To: {task['assignedTo']}")
        report.append(f"  Priority: {task['priority']}")
        report.append(f"  Due Date: {task['dueDate']}")
        report.append("")
    
    # Add completed tasks
    report.append("\nCompleted Tasks:")
    for task in completed_tasks:
        report.append(f"- Title: {task['title']}")
        report.append(f"  Assigned To: {task['assignedTo']}")
        report.append(f"  Priority: {task['priority']}")
        report.append(f"  Due Date: {task['dueDate']}")
        report.append("")

    report_content = "\n".join(report)
    #Send report content to Gemini Flash for summarization
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(f"Summarize the following task report concisely:\n{report_content}")

    summary = response.text if response.text else "Could not generate summary."

    return JSONResponse(content={"message": "Report generation completed", "report": report_content, "summary": summary})

    # return JSONResponse(content={"message": "report generation completed", "report":report_content})

@app.post("/generate_task_report")
async def generate_task_report(request: Request):
    data = await request.json()
    manager_email = data.get("managerEmail")  # Extract manager email from request

    # Fetch counts of tasks assigned by the manager
    in_progress_count = tasks_collection.count_documents({"status": "In Progress", "assignedManager": manager_email})
    completed_count = tasks_collection.count_documents({"status": "Completed", "assignedManager": manager_email})
    
    # Data for pie chart
    labels = ['In Progress', 'Completed']
    counts = [in_progress_count, completed_count]
    colors = ['skyblue', 'lightgreen']
    
    # Plot the pie chart
    plt.figure(figsize=(6, 6))
    plt.pie(counts, labels=labels, autopct='%1.1f%%', colors=colors, startangle=140)
    plt.title('Task Report: In Progress vs Completed')
    plt.axis('equal')  # Equal aspect ratio ensures the pie chart is circular.

    # Save the chart to a BytesIO buffer
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()

    # Encode the image to base64
    image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    buf.close()

    # Generate Insights using Gemini
    model = genai.GenerativeModel("gemini-1.5-flash")
    task_summary_prompt = f"Analyze the task completion status: {completed_count} completed, {in_progress_count} in progress."
    gemini_response = model.generate_content(task_summary_prompt)
    insights = gemini_response.text if hasattr(gemini_response, 'text') else "No insights generated."

    return JSONResponse(content={
        "message": "Task report generated successfully",
        "chart": f"data:image/png;base64,{image_base64}",
        "insights": insights
    })

    # Return the image as a base64 string
    # return JSONResponse(content={
    #     "message": "Task report generated successfully",
    #     "chart": f"data:image/png;base64,{image_base64}"
    # })

@app.post("/refine")
async def refine_task(task_request: TaskRequest):
    short_task_name = task_request.short_task_name.strip()
    
    # Check if the user is greeting
    if short_task_name in ["hi", "hello", "hey"]:
        return {"refined_names": "Hello! I'm here to help you generate task names. Please provide a short task name, and I'll suggest three elaborate task names for you."}

    if not short_task_name:
        raise HTTPException(status_code=400, detail="Task name cannot be empty.")
    
    prompt = f"""
    You are an AI assistant that refines task names in a task management system.
    If the user greets you, respond with a greeting and mention that you are here to help refine task names.
    
    If no greeting is provided, proceed directly to the task.

    Given a short task name, generate three professional, clear, and detailed task names.
    The names should be descriptive but concise, avoiding redundancy.

    Short Task Name: {short_task_name }
    
    Response:
    { "Hello! I'm here to help you refine task names. Here are some suggestions for your task:" if any(greeting in short_task_name.lower() for greeting in ["hello", "hi", "hey", "greetings"]) else "" }

    Short Task Name: {short_task_name}
    Refined Task Names:
    """

    try:
        # Initialize the Gemini model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Generate content using the Gemini model
        response = model.generate_content(prompt)
        
        # Extract the refined task names from the response
        refined_output = response.text.strip()

        return {"refined_names": refined_output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

