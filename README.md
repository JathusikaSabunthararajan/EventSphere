\# EventSphere



\### Agent-Based Venue Booking and Digital Ticketing Platform



EventSphere is a web-based venue booking and digital ticketing platform developed using Python and FastAPI. It uses multiple intelligent agents to manage venue availability, ticket bookings, digital ticket generation, waitlists, and notifications.



\## Technologies Used



\- Python

\- FastAPI

\- SQLAlchemy

\- SQLite

\- Pydantic

\- HTML, CSS and JavaScript

\- Bootstrap

\- QR Code Generation

\- Pytest



\## Intelligent Agents



The system consists of five autonomous agents:



1\. \*\*VenueAgent\*\* – Manages venue availability, scheduling conflicts and private venue hire requests.

2\. \*\*BookingAgent\*\* – Handles ticket bookings, capacity validation and cancellations.

3\. \*\*TicketAgent\*\* – Generates unique QR tickets and manages event check-ins.

4\. \*\*WaitlistAgent\*\* – Manages waiting lists, temporary ticket offers and expired holds.

5\. \*\*NotificationAgent\*\* – Sends notifications based on events received from other agents.



\## Main Features



\- User registration and authentication

\- Role-based access control

\- Venue and event management

\- Ticket booking with capacity protection

\- Simulated payment processing

\- Digital QR ticket generation

\- Ticket validation and check-in

\- Waitlist management

\- Booking cancellation and refund handling

\- Agent-based communication using structured JSON messages

\- Automated waitlist offer expiry

\- Notification management



\## Project Structure



```text

EventSphere/

├── app/

│   ├── agents/

│   ├── database/

│   ├── messaging/

│   ├── models/

│   ├── routers/

│   ├── schemas/

│   ├── services/

│   └── templates/

├── static/

│   ├── css/

│   ├── js/

│   └── images/

├── tests/

├── requirements.txt

├── .gitignore

└── README.md

```



\## Installation and Setup



\### 1. Clone the repository



```bash

git clone https://github.com/JathusikaSabunthararajan/EventSphere.git

cd EventSphere

```



\### 2. Create a virtual environment



```bash

python -m venv venv

```



\### 3. Activate the virtual environment



Windows CMD:



```cmd

venv\\Scripts\\activate

```



\### 4. Install dependencies



```bash

pip install -r requirements.txt

```



\### 5. Run the application



```bash

uvicorn app.main:app --reload

```



\### 6. Open the application



```text

http://127.0.0.1:8000

```



API documentation:



```text

http://127.0.0.1:8000/docs

```



\## Testing



Run the automated tests using:



```bash

python -m pytest -v

```



\## Project Information



\*\*Project Name:\*\* EventSphere  

\*\*Module:\*\* IT4123 – Agent Based Computing  

\*\*Assignment:\*\* ICA 02



\*\*Repository:\*\* https://github.com/JathusikaSabunthararajan/EventSphere



