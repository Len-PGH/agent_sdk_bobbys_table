let selectedDate = null;
let menuData = [];
let calendar; // Make calendar globally accessible
let currentReservationId; // Global reservation ID for payment processing

// Make currentReservationId globally accessible
window.currentReservationId = null;

// Test function to check if modal works
function testModal() {
    console.log('Testing modal...');
    try {
        const modalElement = document.getElementById('newReservationModal');
        console.log('Modal element:', modalElement);
        
        if (modalElement) {
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
            console.log('Modal should be showing now');
        } else {
            console.error('Modal element not found!');
        }
    } catch (error) {
        console.error('Error testing modal:', error);
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing calendar...');
    
    var calendarEl = document.getElementById('calendar');
    console.log('Calendar element:', calendarEl);
    
    // Initialize calendar
    calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',  // Set month view as default
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'  // Month first in the view options
        },
        height: 'auto',
        contentHeight: 'auto',
        expandRows: true,
        aspectRatio: 1.35,
        handleWindowResize: true,
        slotMinTime: '09:00:00',
        slotMaxTime: '21:00:00',
        allDaySlot: false,
        scrollTime: '12:00:00',  // Start scroll position at noon
        scrollTimeReset: false,  // Don't reset scroll position when changing dates
        selectable: true,
        selectMirror: true,
        nowIndicator: true,
        dayMaxEvents: 5,  // Show up to 5 events per day with increased cell height
        moreLinkClick: 'popover',  // Show popover for additional events
        weekNumbers: false,  // Remove week numbers (W22, etc.)
        editable: true,
        eventTimeFormat: { // 12-hour format for events
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        },
        slotLabelFormat: { // 12-hour format for time slots
            hour: 'numeric',
            minute: '2-digit',
            hour12: true
        },
        selectConstraint: {
            startTime: '09:00',
            endTime: '21:00',
            dows: [0, 1, 2, 3, 4, 5, 6]
        },
        businessHours: {
            daysOfWeek: [0, 1, 2, 3, 4, 5, 6],
            startTime: '09:00',
            endTime: '21:00',
        },
        select: function(info) {
            console.log('Calendar select triggered:', info);
            
            try {
                // Show the new reservation modal
                const modalElement = document.getElementById('newReservationModal');
                console.log('Modal element found:', modalElement);
                
                const reservationModal = new bootstrap.Modal(modalElement);
                
                // Set the selected date in the form
                const dateInput = document.getElementById('reservation_date');
                console.log('Date input found:', dateInput);
                dateInput.value = info.startStr.split('T')[0];
                
                // Handle time setting for select dropdown
                const timeStr = info.startStr.split('T')[1] ? info.startStr.split('T')[1].slice(0, 5) : '12:00';
                const timeSelect = document.getElementById('reservation_time');
                console.log('Time select found:', timeSelect);
                
                console.log('Setting time to:', timeStr);
                
                // Find the closest available time slot
                let closestTime = '12:00';
                const availableTimes = Array.from(timeSelect.options).map(option => option.value).filter(value => value);
                
                if (availableTimes.includes(timeStr)) {
                    closestTime = timeStr;
                } else {
                    // Find the closest time slot
                    const selectedMinutes = parseInt(timeStr.split(':')[0]) * 60 + parseInt(timeStr.split(':')[1]);
                    let minDiff = Infinity;
                    
                    availableTimes.forEach(time => {
                        const timeMinutes = parseInt(time.split(':')[0]) * 60 + parseInt(time.split(':')[1]);
                        const diff = Math.abs(timeMinutes - selectedMinutes);
                        if (diff < minDiff) {
                            minDiff = diff;
                            closestTime = time;
                        }
                    });
                }
                
                timeSelect.value = closestTime;
                console.log('Final time set to:', closestTime);
                
                console.log('Showing modal...');
                reservationModal.show();
                
                // Fetch menu items and render party order forms when modal opens
                fetchMenuItems();
                calendar.unselect();
                
            } catch (error) {
                console.error('Error in select handler:', error);
            }
        },
        dateClick: function(info) {
            console.log('Date click triggered:', info);
            
            try {
                // Fallback for when select doesn't work
                const modalElement = document.getElementById('newReservationModal');
                const reservationModal = new bootstrap.Modal(modalElement);
                
                // Set the clicked date
                document.getElementById('reservation_date').value = info.dateStr;
                
                // Set default time to 12:00 PM
                document.getElementById('reservation_time').value = '12:00';
                
                console.log('Showing modal via dateClick...');
                reservationModal.show();
                
                // Fetch menu items and render party order forms when modal opens
                fetchMenuItems();
                
            } catch (error) {
                console.error('Error in dateClick handler:', error);
            }
        },
        eventClick: function(info) {
            // Show event details in the modal
            showReservationDetails(info.event);
        },
        events: '/api/reservations/calendar'
    });

    console.log('Rendering calendar...');
    calendar.render();
    console.log('Calendar rendered');

    // Make testModal available globally for debugging
    window.testModal = testModal;

    // Schedule button event listeners
    document.querySelectorAll('#scheduleBtn, #scheduleBtn2').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const reservationModal = new bootstrap.Modal(document.getElementById('newReservationModal'));
            
            // Set today's date as default
            const today = new Date().toISOString().split('T')[0];
            document.getElementById('reservation_date').value = today;
            
            reservationModal.show();
            // Fetch menu items and render party order forms when modal opens
            fetchMenuItems();
        });
    });

    document.getElementById('partySizeInput').addEventListener('input', function() {
        renderPartyOrderForms();
    });

    // Add event listener for when the new reservation modal is shown
    document.getElementById('newReservationModal').addEventListener('shown.bs.modal', function() {
        fetchMenuItems();
    });

    // Handle old school reservation checkbox
    document.getElementById('oldSchoolReservation').addEventListener('change', function() {
        const orderSection = document.getElementById('orderSection');
        if (this.checked) {
            orderSection.style.display = 'none';
        } else {
            orderSection.style.display = 'block';
            // Re-render party order forms when showing the section
            renderPartyOrderForms();
        }
    });

    // Handle old school reservation checkbox for edit modal
    document.getElementById('editOldSchoolReservation').addEventListener('change', function() {
        const editOrderSection = document.getElementById('editOrderSection');
        if (this.checked) {
            editOrderSection.style.display = 'none';
        } else {
            editOrderSection.style.display = 'block';
            // Re-render party order forms when showing the section
            renderEditPartyOrderForms();
        }
    });

    document.getElementById('reservationForm').addEventListener('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(this);
        
        // Check if this is an old school reservation
        const isOldSchool = document.getElementById('oldSchoolReservation').checked;
        
        if (!isOldSchool) {
            // Collect party orders only if not old school
            const partyOrders = [];
            const partySize = parseInt(document.getElementById('partySizeInput').value) || 1;
            const nameInputs = document.querySelectorAll('.party-member-name');
            for (let i = 0; i < partySize; i++) {
                const name = nameInputs[i].value || '';
                const items = [];
                document.querySelectorAll(`input.menu-qty[data-person="${i}"]`).forEach(function(input) {
                    if (parseInt(input.value) > 0) {
                        items.push({
                            menu_item_id: input.dataset.id,
                            quantity: input.value
                        });
                    }
                });
                partyOrders.push({ name, items });
            }
            formData.append('party_orders', JSON.stringify(partyOrders));
        } else {
            // For old school reservations, send empty party orders
            formData.append('party_orders', JSON.stringify([]));
        }
        fetch('/api/reservations', {
            method: 'POST',
            body: formData
        }).then(resp => resp.json())
          .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert('Error: ' + (data.error || 'Could not create reservation.'));
            }
          });
    });
});

function showReservationDetails(event) {
    const details = document.getElementById('reservationDetails');
    
    // Handle different parameter structures
    let reservationId;
    if (event.id) {
        // Called from calendar event or table with {id: 'x', title: 'y'} format
        reservationId = event.id;
        currentReservationId = reservationId;
        window.currentReservationId = reservationId;
    } else if (typeof event === 'string' || typeof event === 'number') {
        // Called directly with reservation ID
        reservationId = event;
        currentReservationId = reservationId;
        window.currentReservationId = reservationId;
    } else {
        console.error('Invalid event parameter:', event);
        return;
    }
    
    // Fetch reservation and order details from backend
    fetch(`/api/reservations/${reservationId}`)
        .then(resp => resp.json())
        .then(reservation => {
            // Format time in 12-hour format
            const time12hr = new Date(`1970-01-01T${reservation.time}`).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true });
            let html = `
                <div class="mb-3">
                    <h5 class="fw-bold mb-1" style="color: #00e6a7;">Reservation Details</h5>
                    <div><strong>Reservation Number:</strong> <span class="badge bg-primary">${reservation.reservation_number}</span></div>
                    <div><strong>Name:</strong> ${reservation.name}</div>
                    <div><strong>Party Size:</strong> ${reservation.party_size}</div>
                    <div><strong>Date:</strong> ${reservation.date}</div>
                    <div><strong>Time:</strong> ${time12hr}</div>
                    <div><strong>Phone:</strong> ${reservation.phone_number}</div>
                    <div><strong>Status:</strong> ${reservation.status}</div>
                    ${reservation.special_requests ? `<div><strong>Special Requests:</strong> ${reservation.special_requests}</div>` : ''}
                </div>
                <hr class="my-3">
                <h5 class="fw-bold mb-3" style="color: #00e6a7;">Party Orders</h5>
            `;
            let totalBill = 0;
            if (reservation.orders && reservation.orders.length > 0) {
                reservation.orders.forEach((order, idx) => {
                    html += `
                        <div class="card mb-3 bg-dark text-light border-0 shadow-sm">
                            <div class="card-header bg-secondary text-light">
                                <strong>Person ${idx + 1} ${idx === 0 ? '(Reservation Holder)' : ''}</strong> - ${order.person_name || ''}
                            </div>
                            <div class="card-body">
                                <ul class="list-group list-group-flush">
                    `;
                    if (order.items && order.items.length > 0) {
                        order.items.forEach(item => {
                            html += `
                                <li class="list-group-item bg-dark text-light d-flex justify-content-between align-items-center">
                                    <span><strong>${item.menu_item.name}</strong> <small class="text-muted">x${item.quantity}</small></span>
                                    <span class="text-accent">$${(item.price_at_time * item.quantity).toFixed(2)}</span>
                                </li>
                            `;
                        });
                    } else {
                        html += `<li class="list-group-item bg-dark text-light">No items ordered.</li>`;
                    }
                    html += `
                                </ul>
                                <div class="mt-2 text-end"><strong>Total:</strong> <span class="text-accent">$${order.total_amount ? order.total_amount.toFixed(2) : '0.00'}</span></div>
                            </div>
                        </div>
                    `;
                    // Add to total bill
                    totalBill += order.total_amount || 0;
                });
                
                // Add Total Bill section
                html += `
                    <hr class="my-3">
                    <div class="card bg-primary text-light border-0 shadow-lg">
                        <div class="card-body text-center">
                            <h5 class="card-title mb-2"><i class="fas fa-receipt me-2"></i>Total Bill</h5>
                            <h3 class="text-white fw-bold">$${totalBill.toFixed(2)}</h3>
                        </div>
                    </div>
                `;
            } else {
                html += `<div class="text-muted">No party orders found.</div>`;
            }
            details.innerHTML = html;
            
            // Store reservation data globally for payment processing
            window.currentReservationData = {
                ...reservation,
                totalBill: totalBill,
                time: time12hr
            };
            
            // Show appropriate payment button based on payment status
            updatePaymentButtons(reservation.payment_status || 'unpaid');
            
            new bootstrap.Modal(document.getElementById('reservationModal')).show();
        })
        .catch(error => {
            console.error('Error fetching reservation details:', error);
            alert('Error loading reservation details. Please try again.');
        });
}

function updatePaymentButtons(status) {
    const payBillBtn = document.getElementById('payBillBtn');
    const billPaidBtn = document.getElementById('billPaidBtn');

    if (status === 'paid') {
        payBillBtn.style.display = 'none';
        billPaidBtn.style.display = 'inline-block';
    } else {
        payBillBtn.style.display = 'inline-block';
        billPaidBtn.style.display = 'none';
    }
}

function renderPartyOrderForms() {
    const partySize = parseInt(document.getElementById('partySizeInput').value) || 1;
    const partyOrdersDiv = document.getElementById('partyOrders');
    partyOrdersDiv.innerHTML = '';
    for (let i = 0; i < partySize; i++) {
        partyOrdersDiv.innerHTML += `
            <div class="card mb-3 bg-dark text-light border-0 shadow-sm">
                <div class="card-header bg-secondary text-light">
                    <strong>Person ${i + 1} ${i === 0 ? '(Reservation Holder)' : ''}</strong>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">Name</label>
                        <input type="text" class="form-control party-member-name" placeholder="Optional">
                    </div>
                    <div class="menu-items">
                        ${renderMenuItems(i)}
                    </div>
                </div>
            </div>
        `;
    }
}

function renderMenuItems(personIndex) {
    let html = '';
    if (menuData.length > 0) {
        menuData.forEach(category => {
            html += `
                <div class="mb-3">
                    <h6 class="mb-2">${category.name}</h6>
                    <div class="list-group">
            `;
            category.items.forEach(item => {
                html += `
                    <div class="list-group-item bg-dark text-light d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${item.name}</strong>
                            <div class="text-muted small">${item.description}</div>
                            <div class="text-accent">$${item.price.toFixed(2)}</div>
                        </div>
                        <div style="width: 100px;">
                            <input type="number" class="form-control form-control-sm menu-qty" 
                                   value="0" min="0" data-id="${item.id}" data-person="${personIndex}">
                        </div>
                    </div>
                `;
            });
            html += `
                    </div>
                </div>
            `;
        });
    } else {
        html = '<div class="text-muted">Loading menu items...</div>';
    }
    return html;
}

function fetchMenuItems() {
    if (menuData.length === 0) {
        fetch('/api/menu_items')
            .then(resp => resp.json())
            .then(items => {
                // Group items by category
                const categories = {};
                items.forEach(item => {
                    if (!categories[item.category]) {
                        categories[item.category] = {
                            name: item.category,
                            items: []
                        };
                    }
                    categories[item.category].items.push(item);
                });
                menuData = Object.values(categories);
                renderPartyOrderForms();
            });
    }
}

function deleteReservation(reservationId) {
    if (confirm('Are you sure you want to delete this reservation?')) {
        fetch(`/api/reservations/${reservationId}`, {
            method: 'DELETE'
        }).then(response => {
            if (response.ok) {
                window.location.reload();
            } else {
                alert('Failed to delete reservation. Please try again.');
            }
        }).catch(error => {
            console.error('Error:', error);
            alert('An error occurred while deleting the reservation.');
        });
    }
}

function editReservation(reservationId) {
    currentReservationId = reservationId; // Set the global reservation ID
    window.currentReservationId = reservationId; // Also set on window object
    
    // Fetch reservation details
    fetch(`/api/reservations/${reservationId}`)
        .then(resp => resp.json())
        .then(reservation => {
            // Populate form fields
            document.getElementById('editName').value = reservation.name;
            document.getElementById('editPartySize').value = reservation.party_size;
            document.getElementById('editTime').value = reservation.time;
            document.getElementById('editPhone').value = reservation.phone_number;
            document.getElementById('editRequests').value = reservation.special_requests || '';
            document.getElementById('editDate').value = reservation.date;
            
            // Check if this is an old school reservation (no orders)
            const hasOrders = reservation.orders && reservation.orders.length > 0;
            const oldSchoolCheckbox = document.getElementById('editOldSchoolReservation');
            const editOrderSection = document.getElementById('editOrderSection');
            
            if (!hasOrders) {
                // This is an old school reservation
                oldSchoolCheckbox.checked = true;
                editOrderSection.style.display = 'none';
            } else {
                // This has orders, show the order section
                oldSchoolCheckbox.checked = false;
                editOrderSection.style.display = 'block';
            }

            // Ensure menu items are loaded, then render edit form
            if (menuData.length === 0) {
                fetch('/api/menu_items')
                    .then(resp => resp.json())
                    .then(items => {
                        // Group items by category
                        const categories = {};
                        items.forEach(item => {
                            if (!categories[item.category]) {
                                categories[item.category] = {
                                    name: item.category,
                                    items: []
                                };
                            }
                            categories[item.category].items.push(item);
                        });
                        menuData = Object.values(categories);
                        renderEditPartyOrderForms(reservation);
                    });
            } else {
                renderEditPartyOrderForms(reservation);
            }

            // Show modal
            new bootstrap.Modal(document.getElementById('editReservationModal')).show();
        });
}

// Handle form submission
document.getElementById('editReservationForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const formData = new FormData(this);

    // Check if this is an old school reservation
    const isOldSchool = document.getElementById('editOldSchoolReservation').checked;
    
    if (!isOldSchool) {
        // Collect party orders only if not old school
        const partyOrders = [];
        const partySize = parseInt(document.getElementById('editPartySize').value) || 1;
        const nameInputs = document.querySelectorAll('#editPartyOrders .party-member-name');

        for (let i = 0; i < partySize; i++) {
            const name = nameInputs[i].value || '';
            const items = [];
            document.querySelectorAll(`#editPartyOrders input.menu-qty[data-person="${i}"]`).forEach(function(input) {
                if (parseInt(input.value) > 0) {
                    items.push({
                        menu_item_id: input.dataset.id,
                        quantity: input.value
                    });
                }
            });
            partyOrders.push({ name, items });
        }
        formData.append('party_orders', JSON.stringify(partyOrders));
    } else {
        // For old school reservations, send empty party orders
        formData.append('party_orders', JSON.stringify([]));
    }

    // Convert FormData to JSON object
    const jsonData = {};
    for (let [key, value] of formData.entries()) {
        jsonData[key] = value;
    }
    
    // Submit the form
    fetch(`/api/reservations/${currentReservationId}`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(jsonData)
    }).then(resp => {
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        }
        return resp.json();
    })
      .then(data => {
        if (data.success) {
            // Close modal and refresh calendar
            bootstrap.Modal.getInstance(document.getElementById('editReservationModal')).hide();
            calendar.refetchEvents();
            alert('Reservation updated successfully!');
            location.reload();
        } else {
            alert('Error: ' + (data.error || 'Could not update reservation.'));
        }
    }).catch(error => {
        console.error('Error:', error);
        alert('An error occurred while updating the reservation.');
    });
});

// Reschedule reservation function
function rescheduleReservation() {
    if (!currentReservationId) {
        alert('No reservation selected');
        return;
    }
    
    // Close the details modal first
    const detailsModal = bootstrap.Modal.getInstance(document.getElementById('reservationModal'));
    if (detailsModal) {
        detailsModal.hide();
    }
    
    // Wait for the modal to close before opening the edit modal
    setTimeout(() => {
        editReservation(currentReservationId);
    }, 300); // Wait for modal close animation
}

// Cancel reservation function
function cancelReservation() {
    if (!currentReservationId) {
        alert('No reservation selected');
        return;
    }
    
    if (confirm('Are you sure you want to cancel this reservation? This action cannot be undone.')) {
        fetch(`/api/reservations/${currentReservationId}`, {
            method: 'DELETE'
        }).then(response => {
            if (response.ok) {
                // Close the modal
                bootstrap.Modal.getInstance(document.getElementById('reservationModal')).hide();
                // Refresh the calendar
                calendar.refetchEvents();
                // Show success message
                alert('Reservation cancelled successfully');
                // Reload the page to update today\'s reservations
                window.location.reload();
            } else {
                alert('Failed to cancel reservation. Please try again.');
            }
        }).catch(error => {
            console.error('Error:', error);
            alert('An error occurred while cancelling the reservation.');
        });
    }
}

// Render party order forms for edit modal
function renderEditPartyOrderForms(reservation) {
    const partySize = parseInt(reservation.party_size) || 1;
    const partyOrdersDiv = document.getElementById('editPartyOrders');
    partyOrdersDiv.innerHTML = '';
    
    for (let i = 0; i < partySize; i++) {
        const existingOrder = reservation.orders && reservation.orders[i] ? reservation.orders[i] : null;
        
        partyOrdersDiv.innerHTML += `
            <div class="card mb-3 bg-dark text-light border-0 shadow-sm">
                <div class="card-header bg-secondary text-light">
                    <strong>Person ${i + 1} ${i === 0 ? '(Reservation Holder)' : ''}</strong>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">Name</label>
                        <input type="text" class="form-control party-member-name" placeholder="Optional" value="${existingOrder ? existingOrder.person_name || '' : ''}">
                    </div>
                    <div class="menu-items">
                        ${renderEditMenuItems(i, existingOrder)}
                    </div>
                </div>
            </div>
        `;
    }
}

// Render menu items for edit modal with existing quantities
function renderEditMenuItems(personIndex, existingOrder) {
    let html = '';
    if (menuData.length > 0) {
        menuData.forEach(category => {
            html += `
                <div class="mb-3">
                    <h6 class="mb-2">${category.name}</h6>
                    <div class="list-group">
            `;
            category.items.forEach(item => {
                // Find existing quantity for this item
                let existingQuantity = 0;
                if (existingOrder && existingOrder.items) {
                    const existingItem = existingOrder.items.find(orderItem => orderItem.menu_item.id === item.id);
                    if (existingItem) {
                        existingQuantity = existingItem.quantity;
                    }
                }
                
                html += `
                    <div class="list-group-item bg-dark text-light d-flex justify-content-between align-items-center">
                        <div>
                            <strong>${item.name}</strong>
                            <div class="text-muted small">${item.description}</div>
                            <div class="text-accent">$${item.price.toFixed(2)}</div>
                        </div>
                        <div style="width: 100px;">
                            <input type="number" class="form-control form-control-sm menu-qty" 
                                   value="${existingQuantity}" min="0" data-id="${item.id}" data-person="${personIndex}">
                        </div>
                    </div>
                `;
            });
            html += `
                    </div>
                </div>
            `;
        });
    } else {
        html = '<div class="text-muted">Loading menu items...</div>';
    }
    return html;
} 