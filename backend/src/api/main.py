import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from pydantic import BaseModel, Field, EmailStr
from jose import JWTError, jwt
from passlib.context import CryptContext
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session

# Database configuration from environment (PostgreSQL)
DATABASE_URL = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or "postgresql://postgres:password@localhost:5432/cakeshop"
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkeyvalue")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

Base = declarative_base()
engine = sa.create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# CORS origins (can restrict in prod)
origins = ["*"]

app = FastAPI(
    title="Cake Shop Backend",
    description="Backend for cake shop app - catalog, customizations, cart, orders, analytics, and authentication",
    version="1.0.0",
    openapi_tags=[
        {"name": "catalog", "description": "Cake catalog and details"},
        {"name": "auth", "description": "User authentication"},
        {"name": "cart", "description": "Manage user's cart"},
        {"name": "orders", "description": "Order placement and tracking"},
        {"name": "admin", "description": "Admin and analytics"},
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#####
# DATABASE MODELS
#####

class User(Base):
    __tablename__ = "users"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    name = sa.Column(sa.String, nullable=False)
    email = sa.Column(sa.String, unique=True, index=True, nullable=False)
    hashed_password = sa.Column(sa.String, nullable=False)
    is_admin = sa.Column(sa.Boolean, default=False)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    orders = relationship('Order', back_populates='user')
    cart_items = relationship('CartItem', back_populates='user')


class Cake(Base):
    __tablename__ = "cakes"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    name = sa.Column(sa.String, unique=True, nullable=False)
    description = sa.Column(sa.String, nullable=False)
    image_url = sa.Column(sa.String, nullable=True)
    base_price = sa.Column(sa.Numeric(10,2), nullable=False)
    category = sa.Column(sa.String, nullable=True)
    available = sa.Column(sa.Boolean, default=True)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    cake_sizes = relationship('CakeSize', back_populates='cake')
    cake_flavors = relationship('CakeFlavor', back_populates='cake')
    # Toppings are Many-to-Many via cake_toppings association


class Topping(Base):
    __tablename__ = "toppings"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    name = sa.Column(sa.String, unique=True, nullable=False)
    price = sa.Column(sa.Numeric(10,2), nullable=False)
    image_url = sa.Column(sa.String, nullable=True)
    # Many-to-Many relation


cake_toppings = sa.Table(
    "cake_toppings", Base.metadata,
    sa.Column("cake_id", sa.Integer, sa.ForeignKey("cakes.id")),
    sa.Column("topping_id", sa.Integer, sa.ForeignKey("toppings.id"))
)


class CakeSize(Base):
    __tablename__ = "cake_sizes"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    cake_id = sa.Column(sa.Integer, sa.ForeignKey("cakes.id"))
    size = sa.Column(sa.String, nullable=False)  # e.g. "Small", "Medium", "Large"
    price = sa.Column(sa.Numeric(10,2), nullable=False)
    cake = relationship("Cake", back_populates="cake_sizes")


class CakeFlavor(Base):
    __tablename__ = "cake_flavors"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    cake_id = sa.Column(sa.Integer, sa.ForeignKey("cakes.id"))
    flavor = sa.Column(sa.String, nullable=False)  # e.g. "Vanilla", "Chocolate"
    cake = relationship("Cake", back_populates="cake_flavors")


class CartItem(Base):
    __tablename__ = "cart_items"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey("users.id"))
    cake_id = sa.Column(sa.Integer, sa.ForeignKey("cakes.id"))
    size_id = sa.Column(sa.Integer, sa.ForeignKey("cake_sizes.id"))
    flavor_id = sa.Column(sa.Integer, sa.ForeignKey("cake_flavors.id"))
    quantity = sa.Column(sa.Integer, nullable=False, default=1)
    message = sa.Column(sa.String, nullable=True)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="cart_items")
    cake = relationship("Cake")
    size = relationship("CakeSize")
    flavor = relationship("CakeFlavor")
    # toppings: Many-to-Many
    cartitem_toppings = relationship('CartItemTopping', back_populates='cart_item', cascade="all, delete-orphan")


class CartItemTopping(Base):
    __tablename__ = "cartitem_toppings"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    cart_item_id = sa.Column(sa.Integer, sa.ForeignKey("cart_items.id"))
    topping_id = sa.Column(sa.Integer, sa.ForeignKey("toppings.id"))
    cart_item = relationship("CartItem", back_populates="cartitem_toppings")
    topping = relationship("Topping")


class Order(Base):
    __tablename__ = "orders"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey("users.id"))
    delivery_address = sa.Column(sa.String, nullable=False)
    scheduled_time = sa.Column(sa.DateTime, nullable=True)
    total_price = sa.Column(sa.Numeric(10,2), nullable=False)
    status = sa.Column(sa.String, nullable=False, default="Pending")  # Order status field, NOT the FastAPI module
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    updated_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="orders")
    order_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    order_id = sa.Column(sa.Integer, sa.ForeignKey("orders.id"))
    cake_id = sa.Column(sa.Integer, sa.ForeignKey("cakes.id"))
    size_id = sa.Column(sa.Integer, sa.ForeignKey("cake_sizes.id"))
    flavor_id = sa.Column(sa.Integer, sa.ForeignKey("cake_flavors.id"))
    quantity = sa.Column(sa.Integer, nullable=False, default=1)
    price = sa.Column(sa.Numeric(10,2), nullable=False)
    message = sa.Column(sa.String, nullable=True)
    order = relationship("Order", back_populates="order_items")
    cake = relationship("Cake")
    size = relationship("CakeSize")
    flavor = relationship("CakeFlavor")
    # orderitem_toppings: Many-to-Many
    orderitem_toppings = relationship("OrderItemTopping", back_populates="order_item", cascade="all, delete-orphan")


class OrderItemTopping(Base):
    __tablename__ = "orderitem_toppings"
    id = sa.Column(sa.Integer, primary_key=True, index=True)
    order_item_id = sa.Column(sa.Integer, sa.ForeignKey("order_items.id"))
    topping_id = sa.Column(sa.Integer, sa.ForeignKey("toppings.id"))
    order_item = relationship("OrderItem", back_populates="orderitem_toppings")
    topping = relationship("Topping")

# Create DB tables if not exists
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    # Log error, but don't crash
    print("Warning: Failed to create tables. This may be intentional in CI environments:", str(e))

#####
# UTILS for Hashing, Token, User
#####
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# PUBLIC_INTERFACE
def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get a user by their email."""
    return db.query(User).filter(User.email == email).first()

# PUBLIC_INTERFACE
def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate a user, return User if valid else None."""
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user

# PUBLIC_INTERFACE
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Get the current user from a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid authentication.")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication.")
    user = get_user_by_email(db, email)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")
    return user

def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user

def get_current_admin_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not enough privileges")
    return current_user

#####
# PYDANTIC MODELS (SCHEMAS)
#####

class Token(BaseModel):
    access_token: str
    token_type: str

class UserCreate(BaseModel):
    name: str = Field(..., description="User's name")
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="User's raw password")

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_admin: bool

    class Config:
        orm_mode = True

class CakeOut(BaseModel):
    id: int
    name: str
    description: str
    image_url: Optional[str]
    base_price: float
    category: Optional[str]
    available: bool
    sizes: List[Dict[str, Any]]
    flavors: List[Dict[str, Any]]
    toppings: List[Dict[str, Any]]

    class Config:
        orm_mode = True

class ToppingOut(BaseModel):
    id: int
    name: str
    price: float
    image_url: Optional[str]

    class Config:
        orm_mode = True

class CartItemIn(BaseModel):
    cake_id: int
    size_id: int
    flavor_id: int
    quantity: int = 1
    toppings: List[int] = []
    message: Optional[str] = None

class CartItemOut(BaseModel):
    id: int
    cake_id: int
    size_id: int
    flavor_id: int
    quantity: int
    toppings: List[ToppingOut]
    message: Optional[str]

    class Config:
        orm_mode = True

class PlaceOrderIn(BaseModel):
    delivery_address: str
    scheduled_time: Optional[datetime]
    items: List[CartItemIn]

class OrderOut(BaseModel):
    id: int
    user: UserOut
    delivery_address: str
    scheduled_time: Optional[datetime]
    total_price: float
    status: str
    created_at: datetime
    items: List[Any]

    class Config:
        orm_mode = True

class AnalyticsOut(BaseModel):
    total_users: int
    total_orders: int
    total_sales: float
    top_cakes: List[Dict[str, Any]]
    orders_per_day: List[Dict[str, Any]]

    class Config:
        orm_mode = True

#####################################
# ROUTES
#####################################

@app.get("/", tags=["catalog"])
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}

### AUTH

# PUBLIC_INTERFACE
@app.post("/register", summary="Register user", tags=["auth"], response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register a new user (customer-level by default)."""
    db_user = get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=409, detail="Email already registered")
    hashed_pw = get_password_hash(user.password)
    user_obj = User(name=user.name, email=user.email, hashed_password=hashed_pw, is_admin=False)
    db.add(user_obj)
    db.commit()
    db.refresh(user_obj)
    return user_obj

# PUBLIC_INTERFACE
@app.post("/token", summary="User Login (JWT)", tags=["auth"], response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Authenticate via email + password. Returns JWT token."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

### CATALOG

# PUBLIC_INTERFACE
@app.get("/cakes", summary="List all cakes", tags=["catalog"], response_model=List[CakeOut])
def list_cakes(db: Session = Depends(get_db)):
    """Get a list of all cakes with available sizes, flavors, and toppings."""
    cakes = db.query(Cake).filter(Cake.available == True).all()
    result = []
    for cake in cakes:
        sizes = [
            {"id": sz.id, "size": sz.size, "price": float(sz.price)}
            for sz in cake.cake_sizes
        ]
        flavors = [
            {"id": fl.id, "flavor": fl.flavor}
            for fl in cake.cake_flavors
        ]
        # cake_toppings join
        topping_objs = (
            db.query(Topping)
              .join(cake_toppings, (cake_toppings.c.topping_id == Topping.id))
              .filter(cake_toppings.c.cake_id == cake.id)
              .all()
        )
        toppings = [
            {"id": top.id, "name": top.name, "price": float(top.price), "image_url": top.image_url} for top in topping_objs
        ]
        result.append(
            CakeOut(
                id=cake.id,
                name=cake.name,
                description=cake.description,
                image_url=cake.image_url,
                base_price=float(cake.base_price),
                category=cake.category,
                available=cake.available,
                sizes=sizes,
                flavors=flavors,
                toppings=toppings
            )
        )
    return result

# PUBLIC_INTERFACE
@app.get("/cakes/{cake_id}", summary="Retrieve cake detail", tags=["catalog"], response_model=CakeOut)
def get_cake_detail(cake_id: int, db: Session = Depends(get_db)):
    """Get cake detail by ID"""
    cake = db.query(Cake).filter(Cake.id == cake_id, Cake.available == True).first()
    if not cake:
        raise HTTPException(status_code=404, detail="Cake not found")
    sizes = [{"id": sz.id, "size": sz.size, "price": float(sz.price)} for sz in cake.cake_sizes]
    flavors = [{"id": fl.id, "flavor": fl.flavor} for fl in cake.cake_flavors]
    topping_objs = (db.query(Topping)
                    .join(cake_toppings, (cake_toppings.c.topping_id == Topping.id))
                    .filter(cake_toppings.c.cake_id == cake.id)
                    .all())
    toppings = [{"id": top.id, "name": top.name, "price": float(top.price), "image_url": top.image_url} for top in topping_objs]
    return CakeOut(
        id=cake.id,
        name=cake.name,
        description=cake.description,
        image_url=cake.image_url,
        base_price=float(cake.base_price),
        category=cake.category,
        available=cake.available,
        sizes=sizes,
        flavors=flavors,
        toppings=toppings
    )

# PUBLIC_INTERFACE
@app.get("/toppings", summary="List all toppings", tags=["catalog"], response_model=List[ToppingOut])
def list_toppings(db: Session = Depends(get_db)):
    """Get all available toppings."""
    toppings = db.query(Topping).all()
    return toppings

### CART

def get_cart_items_for_user(db: Session, user_id: int):
    """Fetch cart items and toppings for a user."""
    items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    out = []
    for item in items:
        toppings = [db.query(Topping).get(ctt.topping_id) for ctt in item.cartitem_toppings]
        out.append(CartItemOut(
            id=item.id,
            cake_id=item.cake_id,
            size_id=item.size_id,
            flavor_id=item.flavor_id,
            quantity=item.quantity,
            message=item.message,
            toppings=toppings
        ))
    return out

# PUBLIC_INTERFACE
@app.get("/cart", summary="Retrieve user's cart", tags=["cart"], response_model=List[CartItemOut])
def get_cart(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Get current user's cart contents."""
    return get_cart_items_for_user(db, current_user.id)

# PUBLIC_INTERFACE
@app.post("/cart", summary="Add item to cart", tags=["cart"], response_model=CartItemOut)
def add_to_cart(item: CartItemIn, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Add/update an item to the user's cart."""
    cake = db.query(Cake).get(item.cake_id)
    size = db.query(CakeSize).get(item.size_id)
    flavor = db.query(CakeFlavor).get(item.flavor_id)
    if not all([cake, size, flavor]):
        raise HTTPException(status_code=404, detail="Cake/Size/Flavor not found")
    # Save main CartItem
    cart_item = CartItem(
        user_id=current_user.id,
        cake_id=item.cake_id,
        size_id=item.size_id,
        flavor_id=item.flavor_id,
        quantity=item.quantity,
        message=item.message
    )
    db.add(cart_item)
    db.commit()
    db.refresh(cart_item)

    # Save toppings
    for top_id in item.toppings:
        topping = db.query(Topping).get(top_id)
        if not topping:
            continue
        cartitem_topping = CartItemTopping(cart_item_id=cart_item.id, topping_id=top_id)
        db.add(cartitem_topping)
    db.commit()
    db.refresh(cart_item)
    toppings_objs = [db.query(Topping).get(ctt.topping_id) for ctt in cart_item.cartitem_toppings]
    return CartItemOut(
        id=cart_item.id,
        cake_id=cart_item.cake_id,
        size_id=cart_item.size_id,
        flavor_id=cart_item.flavor_id,
        quantity=cart_item.quantity,
        message=cart_item.message,
        toppings=toppings_objs
    )

# PUBLIC_INTERFACE
@app.delete("/cart/{cart_item_id}", summary="Remove item from cart", tags=["cart"])
def remove_from_cart(cart_item_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Remove item from user's cart."""
    cart_item = db.query(CartItem).get(cart_item_id)
    if not cart_item or cart_item.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cart Item not found")
    db.delete(cart_item)
    db.commit()
    return {"message": "Removed from cart"}

# PUBLIC_INTERFACE
@app.delete("/cart", summary="Clear the cart", tags=["cart"])
def clear_cart(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Remove all items from the user's cart."""
    db.query(CartItem).filter(CartItem.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Cart cleared"}

### ORDERS

def calculate_cart_total(db: Session, user_id: int):
    """Calculate total price of the cart."""
    items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    total = 0.0
    for item in items:
        size = db.query(CakeSize).get(item.size_id)
        cake = db.query(Cake).get(item.cake_id)
        q = item.quantity
        price = float(size.price) * q if size else float(cake.base_price) * q
        # topping price
        toppings = [db.query(Topping).get(ctt.topping_id) for ctt in item.cartitem_toppings]
        for topping in toppings:
            price += float(topping.price) * q
        total += price
    return total

# PUBLIC_INTERFACE
@app.post("/orders", summary="Convert cart to order", tags=["orders"])
def place_order(
    payload: PlaceOrderIn,
    current_user: User = Depends(get_current_active_user), 
    db: Session = Depends(get_db)
):
    """Place a new order with the current cart items and delivery details."""
    cart_items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")
    total_price = calculate_cart_total(db, current_user.id)
    order = Order(
        user_id=current_user.id,
        delivery_address=payload.delivery_address,
        scheduled_time=payload.scheduled_time,
        total_price=total_price,
        status="Pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    for item in cart_items:
        size = db.query(CakeSize).get(item.size_id)
        cake = db.query(Cake).get(item.cake_id)
        oitem = OrderItem(
            order_id=order.id,
            cake_id=item.cake_id,
            size_id=item.size_id,
            flavor_id=item.flavor_id,
            quantity=item.quantity,
            price=(float(size.price) if size else float(cake.base_price)),
            message=item.message
        )
        db.add(oitem)
        db.commit()
        db.refresh(oitem)
        for ctt in item.cartitem_toppings:
            oitop = OrderItemTopping(
                order_item_id=oitem.id,
                topping_id=ctt.topping_id
            )
            db.add(oitop)
        db.commit()
    # clear cart
    db.query(CartItem).filter(CartItem.user_id == current_user.id).delete()
    db.commit()
    return {"order_id": order.id, "status": order.status, "total": total_price}

# PUBLIC_INTERFACE
@app.get("/orders", summary="Get user's orders", tags=["orders"])
def list_my_orders(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Returns a list of the user's orders and their statuses."""
    orders = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.created_at.desc()).all()
    result = []
    for order in orders:
        items = []
        for item in order.order_items:
            toppings = [db.query(Topping).get(ot.topping_id) for ot in item.orderitem_toppings]
            items.append({
                "cake_id": item.cake_id,
                "size_id": item.size_id,
                "flavor_id": item.flavor_id,
                "quantity": item.quantity,
                "toppings": [{"id": t.id, "name": t.name, "price": float(t.price)} for t in toppings if t],
                "message": item.message,
            })
        result.append({
            "id": order.id,
            "delivery_address": order.delivery_address,
            "scheduled_time": order.scheduled_time,
            "total_price": float(order.total_price),
            "status": order.status,
            "created_at": order.created_at,
            "items": items
        })
    return result

# PUBLIC_INTERFACE
@app.get("/orders/{order_id}", summary="Get an order's detail (user)", tags=["orders"])
def get_order_detail(order_id: int, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    """Get details of a single order if it belongs to the current user."""
    order = db.query(Order).get(order_id)
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    items = []
    for item in order.order_items:
        toppings = [db.query(Topping).get(ot.topping_id) for ot in item.orderitem_toppings]
        items.append({
            "cake_id": item.cake_id,
            "size_id": item.size_id,
            "flavor_id": item.flavor_id,
            "quantity": item.quantity,
            "toppings": [{"id": t.id, "name": t.name, "price": float(t.price)} for t in toppings if t],
            "message": item.message,
        })
    return {
        "id": order.id,
        "delivery_address": order.delivery_address,
        "scheduled_time": order.scheduled_time,
        "total_price": float(order.total_price),
        "status": order.status,
        "created_at": order.created_at,
        "items": items
    }

### Admin/Analytics

# PUBLIC_INTERFACE
@app.get("/admin/orders", summary="List all orders (admin)", tags=["admin"])
def admin_all_orders(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """List all orders in system (admin only)."""
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    result = []
    for order in orders:
        user = db.query(User).get(order.user_id)
        items = []
        for item in order.order_items:
            toppings = [db.query(Topping).get(ot.topping_id) for ot in item.orderitem_toppings]
            items.append({
                "cake_id": item.cake_id,
                "size_id": item.size_id,
                "flavor_id": item.flavor_id,
                "quantity": item.quantity,
                "toppings": [{"id": t.id, "name": t.name, "price": float(t.price)} for t in toppings if t],
                "message": item.message,
            })
        result.append({
            "id": order.id,
            "user": {
                "id": user.id if user else None,
                "name": user.name if user else None,
                "email": user.email if user else None,
            },
            "delivery_address": order.delivery_address,
            "scheduled_time": order.scheduled_time,
            "total_price": float(order.total_price),
            "status": order.status,
            "created_at": order.created_at,
            "items": items
        })
    return result

# PUBLIC_INTERFACE
@app.patch("/admin/orders/{order_id}/status", summary="Update order status (admin)", tags=["admin"])
def update_order_status(order_id: int, order_status: str = Body(..., embed=True), current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Update the status of an order. Status: Pending/Preparing/Ready/Out for delivery/Delivered."""
    order = db.query(Order).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = order_status
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return {"order_id": order.id, "status": order.status}

# PUBLIC_INTERFACE
@app.get("/admin/analytics", summary="Analytics dashboard (admin)", tags=["admin"], response_model=AnalyticsOut)
def get_analytics(current_user: User = Depends(get_current_admin_user), db: Session = Depends(get_db)):
    """Return analytics for admin dashboard."""
    total_users = db.query(User).count()
    total_orders = db.query(Order).count()
    total_sales = db.query(sa.func.sum(Order.total_price)).scalar() or 0
    # Top 5 cakes by quantity sold
    top_cakes_raw = (
        db.query(OrderItem.cake_id, sa.func.sum(OrderItem.quantity).label("quantity"))
        .group_by(OrderItem.cake_id)
        .order_by(sa.desc("quantity"))
        .limit(5)
        .all()
    )
    top_cakes = []
    for cake_id, qty in top_cakes_raw:
        cake = db.query(Cake).get(cake_id)
        if cake:
            top_cakes.append({
                "cake_id": cake_id,
                "cake_name": cake.name,
                "quantity_sold": qty
            })
    # Orders per day (last 7 days)
    now = datetime.utcnow()
    orders_per_day = []
    for i in range(6,-1,-1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = (now - timedelta(days=i)).replace(hour=23, minute=59, second=59, microsecond=999999)
        count = db.query(Order).filter(Order.created_at >= day_start, Order.created_at <= day_end).count()
        orders_per_day.append({
            "date": day_start.date().isoformat(),
            "order_count": count
        })
    return AnalyticsOut(
        total_users=total_users,
        total_orders=total_orders,
        total_sales=float(total_sales),
        top_cakes=top_cakes,
        orders_per_day=orders_per_day
    )

## SWAGGER / DOCS - notes for websocket or advanced features
@app.get("/docs/ws", summary="WebSocket API Usage (Not Implemented Here)", tags=["catalog"])
def ws_usage_doc():
    """
    WebSocket API is not implemented in this backend.

    Real-time order tracking and admin cockpit could be implemented via WebSocket endpoints in the future.
    """
    return {
        "message": "WebSocket endpoints are not implemented in this backend. Consider polling the REST API."
    }
