
// EventSphere Login Functionality

const loginForm = document.getElementById("loginForm");

if (loginForm) {

    loginForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        const email = document.getElementById("email").value;
        const password = document.getElementById("password").value;

        const message = document.getElementById("loginMessage");

        message.textContent = "Logging in...";
        message.style.color = "#6366f1";

        try {

            const response = await fetch("/auth/login", {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    email: email,
                    password: password
                })
            });

            const data = await response.json();

            if (response.ok) {

                // Save JWT token
                localStorage.setItem(
                    "access_token",
                    data.access_token
                );

                message.textContent = "Login successful!";
                message.style.color = "green";

                // Redirect to homepage
                setTimeout(() => {
                    window.location.href = "/dashboard";
                }, 1000);

            } else {

                message.textContent =
                    data.detail || "Login failed.";

                message.style.color = "red";
            }

        } catch (error) {

            message.textContent =
                "Unable to connect to the server.";

            message.style.color = "red";

            console.error(error);
        }

    });

}


// EventSphere Registration Functionality

const registerForm = document.getElementById("registerForm");

if (registerForm) {

    registerForm.addEventListener("submit", async function(event) {

        event.preventDefault();

        const username = document.getElementById("username").value;
        const email = document.getElementById("registerEmail").value;
        const password = document.getElementById("registerPassword").value;

        const message = document.getElementById("registerMessage");

        message.textContent = "Creating account...";
        message.style.color = "#6366f1";

        try {

            const response = await fetch("/auth/register", {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    username: username,
                    email: email,
                    password: password
                })

            });

            const data = await response.json();

            if (response.ok) {

                message.textContent =
                    "Account created successfully! Please login.";

                message.style.color = "green";

                registerForm.reset();

                setTimeout(() => {
                    window.location.href = "/login";
                }, 1500);

            } else {

                message.textContent =
                    data.detail || "Registration failed.";

                message.style.color = "red";

            }

        } catch (error) {

            message.textContent =
                "Unable to connect to the server.";

            message.style.color = "red";

            console.error(error);

        }

    });

}


async function loadDashboard() {

    const dashboardUsername =
        document.getElementById("dashboardUsername");

    if (!dashboardUsername) return;

    const token = localStorage.getItem("access_token");

    if (!token) {
        window.location.href = "/login";
        return;
    }

    try {
        const response = await fetch("/auth/me", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (!response.ok) {
            localStorage.removeItem("access_token");
            window.location.href = "/login";
            return;
        }

        const user = await response.json();

        document.getElementById("dashboardUsername").textContent = user.username;
        document.getElementById("userUsername").textContent = user.username;
        document.getElementById("userEmail").textContent = user.email;
        document.getElementById("userRole").textContent = user.role;

    } catch (error) {
        console.error("Dashboard error:", error);
    }
}

loadDashboard();


// Logout functionality

const logoutButton = document.getElementById("logoutButton");

if (logoutButton) {

    logoutButton.addEventListener("click", function() {

        localStorage.removeItem("access_token");

        window.location.href = "/login";

    });

}

loadDashboard();


async function loadMyBookings() {

    const container = document.getElementById("bookingsContainer");

    if (!container) return;

    const token = localStorage.getItem("access_token");

    if (!token) {
        window.location.href = "/login";
        return;
    }

    try {

        const response = await fetch("/bookings/my", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error("Unable to load bookings.");
        }

        const data = await response.json();

        document.getElementById("bookingLoading").textContent =
            `Total bookings: ${data.total_bookings}`;

        if (data.bookings.length === 0) {

            container.innerHTML = `
                <p>You have not made any bookings yet.</p>
            `;

            return;
        }

        container.innerHTML = data.bookings.map(booking => `
            <div class="booking-item">
                <h3>Booking #${booking.booking_id}</h3>
                <p>Event ID: ${booking.event_id}</p>
                <p>Tickets: ${booking.quantity}</p>
                <p>Total: Rs. ${booking.total_amount}</p>
                <p>Status: ${booking.status}</p>
            </div>
        `).join("");

    } catch (error) {

        document.getElementById("bookingLoading").textContent =
            error.message;

    }
}

loadMyBookings();


async function loadMyTickets() {

    const container = document.getElementById("ticketsContainer");

    if (!container) return;

    const token = localStorage.getItem("access_token");

    if (!token) {
        window.location.href = "/login";
        return;
    }

    try {

        const response = await fetch("/tickets/my", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error("Unable to load tickets.");
        }

        const data = await response.json();

        document.getElementById("ticketLoading").textContent =
            `Total tickets: ${data.total_tickets}`;

        if (data.tickets.length === 0) {

            container.innerHTML =
                "<p>You have no digital tickets yet.</p>";

            return;
        }

        container.innerHTML = data.tickets.map(ticket => `
            <div class="booking-item">
                <h3>Ticket #${ticket.ticket_id}</h3>
                <p>Booking ID: ${ticket.booking_id}</p>
                <p>Status: ${ticket.status}</p>
                <p>QR Code: ${ticket.qr_code}</p>
            </div>
        `).join("");

    } catch (error) {

        document.getElementById("ticketLoading").textContent =
            error.message;

    }
}

loadMyTickets();


async function loadMyWaitlist() {

    const container = document.getElementById("waitlistContainer");

    if (!container) return;

    const token = localStorage.getItem("access_token");

    if (!token) {
        window.location.href = "/login";
        return;
    }

    try {

        const response = await fetch("/waitlist/my", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error("Unable to load waitlist.");
        }

        const data = await response.json();

        document.getElementById("waitlistLoading").textContent =
            `Total waitlist entries: ${data.total_entries}`;

        if (data.waitlist.length === 0) {

            container.innerHTML =
                "<p>You are not currently in any waitlist.</p>";

            return;
        }

        container.innerHTML = data.waitlist.map(entry => `
            <div class="booking-item">
                <h3>Waitlist Entry #${entry.entry_id}</h3>
                <p>Event ID: ${entry.event_id}</p>
                <p>Ticket Category: ${entry.ticket_category_id}</p>
                <p>Status: ${entry.status}</p>
                <p>Hold Expires: ${entry.hold_expires_at || "N/A"}</p>
            </div>
        `).join("");

    } catch (error) {

        document.getElementById("waitlistLoading").textContent =
            error.message;

    }
}

loadMyWaitlist();



async function loadMyNotifications() {

    const container = document.getElementById("notificationsContainer");

    if (!container) return;

    const token = localStorage.getItem("access_token");

    if (!token) {
        window.location.href = "/login";
        return;
    }

    try {

        const response = await fetch("/notifications/my", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (!response.ok) {
            throw new Error("Unable to load notifications.");
        }

        const data = await response.json();

        document.getElementById("notificationLoading").textContent =
            `Total notifications: ${data.total_notifications}`;

        if (data.notifications.length === 0) {

            container.innerHTML =
                "<p>You have no new notifications.</p>";

            return;
        }

        container.innerHTML = data.notifications.map(notification => `
            <div class="booking-item">
                <h3>Notification #${notification.id}</h3>
                <p>${notification.message}</p>
            </div>
        `).join("");

    } catch (error) {

        document.getElementById("notificationLoading").textContent =
            error.message;

    }
}

loadMyNotifications();


async function loadPublicEvents() {

    const container = document.getElementById("publicEventsContainer");

    if (!container) return;

    try {

        const response = await fetch("/events");

        if (!response.ok) {
            throw new Error("Unable to load events.");
        }

        const data = await response.json();

        if (data.events.length === 0) {

            container.innerHTML = `
                <div class="event-placeholder">
                    <div>🎭</div>
                    <h3>Exciting Events Coming Soon</h3>
                    <p>Stay tuned for upcoming events on EventSphere.</p>
                </div>
            `;

            return;
        }

        container.innerHTML = data.events.map(event => `
            <div class="event-card">

                <div class="event-card-icon">🎉</div>

                <div class="event-card-content">

                    <span class="event-category">
                        ${event.category}
                    </span>

                    <h3>${event.title}</h3>

                    <p>${event.description}</p>

                    <p>
                        <strong>Start:</strong>
                        ${new Date(event.start_time).toLocaleString()}
                    </p>

                    <p>
                        <strong>End:</strong>
                        ${new Date(event.end_time).toLocaleString()}
                    </p>

                    <a href="/login" class="btn btn-primary">
                        Book Tickets
                    </a>

                </div>

            </div>
        `).join("");

    } catch (error) {

        container.innerHTML = `
            <div class="event-placeholder">
                <h3>Unable to Load Events</h3>
                <p>${error.message}</p>
            </div>
        `;

    }
}

loadPublicEvents();
