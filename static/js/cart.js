// Shopping Cart System
class ShoppingCart {
    constructor() {
        this.items = JSON.parse(localStorage.getItem('cart')) || [];
        this.updateCartDisplay();
        this.initializeEventListeners();
    }

    addItem(itemId, name, price, description) {
        console.log('Adding item:', itemId, name, price); // Debug log
        const existingItem = this.items.find(item => item.id === itemId);
        
        if (existingItem) {
            existingItem.quantity += 1;
            console.log('Updated existing item quantity to:', existingItem.quantity); // Debug log
        } else {
            this.items.push({
                id: itemId,
                name: name,
                price: price,
                description: description,
                quantity: 1
            });
            console.log('Added new item to cart'); // Debug log
        }
        
        this.saveCart();
        this.updateCartDisplay();
        this.showAddedFeedback();
    }



    updateQuantity(itemId, quantity) {
        const item = this.items.find(item => item.id === itemId);
        if (item) {
            if (quantity <= 0) {
                this.removeItem(itemId);
            } else {
                item.quantity = quantity;
                this.saveCart();
                this.updateCartDisplay();
                
                // If cart modal is open, refresh it
                const cartModal = document.getElementById('cartModal');
                if (cartModal && cartModal.classList.contains('show')) {
                    this.refreshCartModal();
                }
            }
        }
    }

    removeItem(itemId) {
        this.items = this.items.filter(item => item.id !== itemId);
        this.saveCart();
        this.updateCartDisplay();
        
        // If cart modal is open, refresh it
        const cartModal = document.getElementById('cartModal');
        if (cartModal && cartModal.classList.contains('show')) {
            this.refreshCartModal();
        }
    }

    refreshCartModal() {
        // Update just the cart items and summary sections
        const cartItemsContainer = document.querySelector('.cart-items');
        const cartSummary = document.querySelector('.cart-summary');
        
        if (!cartItemsContainer || !cartSummary) return;
        
        // Generate new cart items HTML
        const cartItems = this.items.map(item => `
            <div class="cart-item d-flex justify-content-between align-items-center mb-3 p-3 bg-dark rounded">
                <div class="flex-grow-1">
                    <h6 class="mb-1">${item.name}</h6>
                    <small class="text-muted">${item.description}</small>
                    <div class="text-accent fw-bold">$${item.price.toFixed(2)}</div>
                </div>
                <div class="d-flex align-items-center">
                    <button class="btn btn-sm btn-outline-light me-2 qty-decrease" data-item-id="${item.id}" data-quantity="${item.quantity}">
                        <i class="fas fa-minus"></i>
                    </button>
                    <span class="mx-2 fw-bold">${item.quantity}</span>
                    <button class="btn btn-sm btn-outline-light me-2 qty-increase" data-item-id="${item.id}" data-quantity="${item.quantity}">
                        <i class="fas fa-plus"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger item-remove" data-item-id="${item.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
        
        // Update cart items
        cartItemsContainer.innerHTML = cartItems;
        
        // Update cart summary
        cartSummary.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <h5 class="mb-0">Total: <span class="text-accent">$${this.getTotal().toFixed(2)}</span></h5>
                <span class="text-muted">${this.getItemCount()} items</span>
            </div>
        `;
        
        // Re-add event listeners for the new buttons
        this.addCartEventListeners();
    }

    getTotal() {
        return this.items.reduce((total, item) => total + (item.price * item.quantity), 0);
    }

    getItemCount() {
        return this.items.reduce((count, item) => count + item.quantity, 0);
    }

    clearCart() {
        this.items = [];
        this.saveCart();
        this.updateCartDisplay();
    }

    saveCart() {
        localStorage.setItem('cart', JSON.stringify(this.items));
    }

    updateCartDisplay() {
        const cartBadge = document.getElementById('cart-badge');
        const cartButton = document.getElementById('cart-button');
        const itemCount = this.getItemCount();
        
        if (cartBadge) {
            cartBadge.textContent = itemCount;
            cartBadge.style.display = itemCount > 0 ? 'inline' : 'none';
        }
        
        if (cartButton) {
            cartButton.style.display = itemCount > 0 ? 'inline-block' : 'none';
        }
    }

    showAddedFeedback() {
        // Show a toast notification
        const toast = document.createElement('div');
        toast.className = 'toast-notification';
        toast.innerHTML = `
            <div class="alert alert-success alert-dismissible fade show" role="alert">
                <i class="fas fa-check-circle me-2"></i>
                Item added to cart!
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
        `;
        
        document.body.appendChild(toast);
        
        // Auto remove after 3 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 3000);
    }

    renderCartModal() {
        const cartItems = this.items.map(item => `
            <div class="cart-item d-flex justify-content-between align-items-center mb-3 p-3 bg-dark rounded">
                <div class="flex-grow-1">
                    <h6 class="mb-1">${item.name}</h6>
                    <small class="text-muted">${item.description}</small>
                    <div class="text-accent fw-bold">$${item.price.toFixed(2)}</div>
                </div>
                <div class="d-flex align-items-center">
                    <button class="btn btn-sm btn-outline-light me-2 qty-decrease" data-item-id="${item.id}" data-quantity="${item.quantity}">
                        <i class="fas fa-minus"></i>
                    </button>
                    <span class="mx-2 fw-bold">${item.quantity}</span>
                    <button class="btn btn-sm btn-outline-light me-2 qty-increase" data-item-id="${item.id}" data-quantity="${item.quantity}">
                        <i class="fas fa-plus"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger item-remove" data-item-id="${item.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');

        const modalContent = `
            <div class="modal fade" id="cartModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content bg-modal text-light rounded-4">
                        <div class="modal-header border-0" style="background: #232b3e;">
                            <h5 class="modal-title">
                                <i class="fas fa-shopping-cart me-2"></i>Your Order
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            ${this.items.length > 0 ? `
                                <div class="cart-items mb-4">
                                    ${cartItems}
                                </div>
                                <div class="cart-summary p-3 bg-secondary rounded mb-4">
                                    <div class="d-flex justify-content-between align-items-center">
                                        <h5 class="mb-0">Total: <span class="text-accent">$${this.getTotal().toFixed(2)}</span></h5>
                                        <span class="text-muted">${this.getItemCount()} items</span>
                                    </div>
                                </div>
                                <div class="order-type mb-4">
                                    <h6 class="mb-3">Order Type</h6>
                                    <div class="row">
                                        <div class="col-md-6">
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="orderType" id="pickup" value="pickup" checked>
                                                <label class="form-check-label" for="pickup">
                                                    <i class="fas fa-store me-2"></i>Pickup
                                                </label>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="form-check">
                                                <input class="form-check-input" type="radio" name="orderType" id="delivery" value="delivery">
                                                <label class="form-check-label" for="delivery">
                                                    <i class="fas fa-truck me-2"></i>Delivery
                                                </label>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div class="order-timing mb-4">
                                    <h6 class="mb-3">When do you want your order?</h6>
                                    <div class="row mb-3">
                                        <div class="col-md-6">
                                            <label class="form-label">Date</label>
                                            <input type="date" class="form-control" id="orderDate" required>
                                        </div>
                                        <div class="col-md-6">
                                            <label class="form-label">Time</label>
                                            <select class="form-control" id="orderTime" required>
                                                <option value="">Select time</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                <div class="customer-info">
                                    <h6 class="mb-3">Customer Information</h6>
                                    <div class="row mb-3">
                                        <div class="col-md-6">
                                            <label class="form-label">Name</label>
                                            <input type="text" class="form-control" id="customerName" required>
                                        </div>
                                        <div class="col-md-6">
                                            <label class="form-label">Phone</label>
                                            <input type="tel" class="form-control" id="customerPhone" required>
                                        </div>
                                    </div>
                                    <div class="delivery-address" id="deliveryAddress" style="display: none;">
                                        <div class="mb-3">
                                            <label class="form-label">Delivery Address</label>
                                            <textarea class="form-control" id="customerAddress" rows="3"></textarea>
                                        </div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Special Instructions (Optional)</label>
                                        <textarea class="form-control" id="specialInstructions" rows="2"></textarea>
                                    </div>
                                </div>
                            ` : `
                                <div class="text-center py-4">
                                    <i class="fas fa-shopping-cart fa-3x mb-3 text-muted"></i>
                                    <h5 class="text-muted">Your cart is empty</h5>
                                    <p class="text-muted">Add some delicious items from our menu!</p>
                                </div>
                            `}
                        </div>
                        <div class="modal-footer border-0" style="background: #232b3e;">
                            ${this.items.length > 0 ? `
                                <button type="button" class="btn btn-outline-light" onclick="cart.clearCart(); bootstrap.Modal.getInstance(document.getElementById('cartModal')).hide();">
                                    Clear Cart
                                </button>
                                <button type="button" class="btn btn-accent btn-lg" onclick="cart.submitOrder()">
                                    <i class="fas fa-credit-card me-2"></i>Place Order
                                </button>
                            ` : `
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            `}
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('cartModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add new modal to body
        document.body.insertAdjacentHTML('beforeend', modalContent);
    }

    showCart() {
        this.renderCartModal();
        
        // Set default date to today
        const today = new Date();
        const dateInput = document.getElementById('orderDate');
        if (dateInput) {
            dateInput.value = today.toISOString().split('T')[0];
            dateInput.min = today.toISOString().split('T')[0]; // Can't order in the past
        }
        
        // Populate time options
        this.populateTimeOptions();
        
        // Add event listeners for quantity buttons
        this.addCartEventListeners();
        
        const modal = new bootstrap.Modal(document.getElementById('cartModal'));
        modal.show();
    }

    populateTimeOptions() {
        const timeSelect = document.getElementById('orderTime');
        if (!timeSelect) return;
        
        // Clear existing options except the first one
        timeSelect.innerHTML = '<option value="">Select time</option>';
        
        // Generate time slots from 9:00 AM to 9:00 PM in 30-minute intervals
        for (let hour = 9; hour <= 21; hour++) {
            for (let minute = 0; minute < 60; minute += 30) {
                const time24 = `${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
                const timeObj = new Date();
                timeObj.setHours(hour, minute);
                const time12 = timeObj.toLocaleTimeString('en-US', { 
                    hour: 'numeric', 
                    minute: '2-digit',
                    hour12: true 
                });
                
                const option = document.createElement('option');
                option.value = time24;
                option.textContent = time12;
                timeSelect.appendChild(option);
            }
        }
    }

    addCartEventListeners() {
        // Quantity decrease buttons
        document.querySelectorAll('.qty-decrease').forEach(button => {
            button.addEventListener('click', (e) => {
                const itemId = e.target.closest('button').dataset.itemId;
                const currentQty = parseInt(e.target.closest('button').dataset.quantity);
                this.updateQuantity(itemId, currentQty - 1);
            });
        });
        
        // Quantity increase buttons
        document.querySelectorAll('.qty-increase').forEach(button => {
            button.addEventListener('click', (e) => {
                const itemId = e.target.closest('button').dataset.itemId;
                const currentQty = parseInt(e.target.closest('button').dataset.quantity);
                this.updateQuantity(itemId, currentQty + 1);
            });
        });
        
        // Remove item buttons
        document.querySelectorAll('.item-remove').forEach(button => {
            button.addEventListener('click', (e) => {
                const itemId = e.target.closest('button').dataset.itemId;
                this.removeItem(itemId);
            });
        });
    }

    submitOrder() {
        const orderType = document.querySelector('input[name="orderType"]:checked').value;
        const orderDate = document.getElementById('orderDate').value;
        const orderTime = document.getElementById('orderTime').value;
        const customerName = document.getElementById('customerName').value;
        const customerPhone = document.getElementById('customerPhone').value;
        const customerAddress = document.getElementById('customerAddress').value;
        const specialInstructions = document.getElementById('specialInstructions').value;

        if (!orderDate || !orderTime) {
            alert('Please select when you want your order.');
            return;
        }

        if (!customerName || !customerPhone) {
            alert('Please fill in your name and phone number.');
            return;
        }

        if (orderType === 'delivery' && !customerAddress) {
            alert('Please provide a delivery address.');
            return;
        }

        const orderData = {
            items: this.items,
            orderType: orderType,
            orderDate: orderDate,
            orderTime: orderTime,
            customerName: customerName,
            customerPhone: customerPhone,
            customerAddress: orderType === 'delivery' ? customerAddress : null,
            specialInstructions: specialInstructions,
            total: this.getTotal(),
            timestamp: new Date().toISOString()
        };

        // Submit order to backend
        fetch('/api/orders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(orderData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`Order placed successfully! Order #${data.orderId}\n\nEstimated ${orderType === 'pickup' ? 'pickup' : 'delivery'} time: ${data.estimatedTime} minutes.`);
                this.clearCart();
                bootstrap.Modal.getInstance(document.getElementById('cartModal')).hide();
            } else {
                alert('Error placing order: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error placing order. Please try again.');
        });
    }

    initializeEventListeners() {
        // Listen for order type changes
        document.addEventListener('change', function(e) {
            if (e.target.name === 'orderType') {
                const deliveryAddress = document.getElementById('deliveryAddress');
                if (deliveryAddress) {
                    deliveryAddress.style.display = e.target.value === 'delivery' ? 'block' : 'none';
                }
            }
        });
    }
}

// Initialize cart when DOM is loaded
let cart;
document.addEventListener('DOMContentLoaded', function() {
    if (!cart) {
        cart = new ShoppingCart();
    }
}); 