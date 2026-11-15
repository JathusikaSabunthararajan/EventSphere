
async function loadMyTickets() {

    const container = document.getElementById("ticketsContainer");

    if (!container) return;

    const token = localStorage.getItem("access_token");

    if (!token) {
        container.innerHTML = `
            <p>Please login to view your tickets.</p>
            <a href="/login">Login</a>
        `;
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

        if (data.total_tickets === 0) {
            container.innerHTML = `
                <div class="event-placeholder">
                    <h3>No Tickets Yet</h3>
                    <p>Your digital tickets will appear here after booking.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <h3>Total Tickets: ${data.total_tickets}</h3>

            <div class="event-grid">
                ${data.tickets.map(ticket => `
                    <div class="event-card">

                        <h3>Ticket #${ticket.ticket_id}</h3>

                        <p>Booking ID: ${ticket.booking_id}</p>

                        <img
                            src="${ticket.qr_image}"
                            alt="Ticket QR Code"
                            width="200"
                            height="200"
                        >

                        <p>
                            Status:
                            <strong>${ticket.status}</strong>
                        </p>

                    </div>
                `).join("")}
            </div>
        `;

    } catch (error) {

        container.innerHTML = `
            <p>${error.message}</p>
        `;

    }
}

loadMyTickets();
