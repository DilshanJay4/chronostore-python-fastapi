"""Seed script to populate initial development and demo data for ChronoStore API."""

from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import get_session_factory
from app.domain.enums import (
    AdjustmentReason,
    InventoryMovementType,
    ProductStatus,
    UserRole,
    WatchMovement,
)
from app.models.entities import (
    Address,
    Brand,
    Cart,
    Category,
    InventoryItem,
    InventoryMovement,
    Product,
    User,
)


def seed_database() -> None:
    session_factory = get_session_factory()

    with session_factory() as session:
        # 1. Admin User
        admin_email = "admin@chronostore.lk"
        admin = session.execute(select(User).where(User.email == admin_email)).scalar_one_or_none()

        if not admin:
            print(f"Creating default admin account: {admin_email}")
            admin = User(
                email=admin_email,
                password_hash=hash_password("Admin@Chrono2026"),
                full_name="ChronoStore Admin",
                phone="+94112345678",
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(admin)
            session.flush()

            # Cart for admin
            session.add(Cart(user_id=admin.id))
        else:
            print(f"Admin account ({admin_email}) already exists.")

        # 2. Demo Customer User
        customer_email = "demo@chronostore.lk"
        customer = session.execute(
            select(User).where(User.email == customer_email)
        ).scalar_one_or_none()

        if not customer:
            print(f"Creating demo customer account: {customer_email}")
            customer = User(
                email=customer_email,
                password_hash=hash_password("Customer@Chrono2026"),
                full_name="Nuwan Jayawardana",
                phone="+94771234567",
                role=UserRole.CUSTOMER,
                is_active=True,
            )
            session.add(customer)
            session.flush()

            session.add(Cart(user_id=customer.id))

            # Default address for customer
            addr = Address(
                user_id=customer.id,
                label="Home",
                recipient_name="Nuwan Jayawardana",
                phone="+94771234567",
                street_line1="No. 45, Duplication Road",
                street_line2="Bambalapitiya",
                city="Colombo",
                postal_code="00400",
                province="Western",
                country_code="LK",
                is_default=True,
            )
            session.add(addr)
        else:
            print(f"Demo customer account ({customer_email}) already exists.")

        # 3. Brands
        brands_data = [
            ("Seiko", "seiko", "Japanese precision, craftsmanship, and dive heritage."),
            ("Tissot", "tissot", "Swiss watchmaking excellence since 1853."),
            ("Casio", "casio", "Durable quartz timepieces, G-Shock, and Edifice lines."),
            ("Citizen", "citizen", "Pioneers of light-powered Eco-Drive technology."),
            ("Orient", "orient", "Mechanical in-house manufacture timepieces."),
        ]
        brand_map = {}
        for name, slug, desc in brands_data:
            b = session.execute(select(Brand).where(Brand.slug == slug)).scalar_one_or_none()
            if not b:
                b = Brand(name=name, slug=slug, description=desc, is_active=True)
                session.add(b)
                session.flush()
            brand_map[slug] = b

        # 4. Categories
        categories_data = [
            ("Dive Watches", "dive-watches", "ISO certified water-resistant tool watches."),
            ("Dress Watches", "dress-watches", "Elegant timepieces suitable for formal occasions."),
            ("Chronographs", "chronographs", "Stopwatch function precision timing."),
            ("Sports Watches", "sports-watches", "Rugged daily wear luxury sports timepieces."),
        ]
        category_map = {}
        for name, slug, desc in categories_data:
            c = session.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()
            if not c:
                c = Category(name=name, slug=slug, description=desc, is_active=True)
                session.add(c)
                session.flush()
            category_map[slug] = c

        # 5. Products
        watches = [
            {
                "sku": "SEIKO-PROSPEX-TURTLE",
                "name": "Seiko Prospex SRPE93 'Turtle' Diver",
                "model": "SRPE93",
                "description": (
                    "Automatic 4R36 movement, cushion case, 200m ISO diver rated with "
                    "Lumibrite hands and markers."
                ),
                "brand_slug": "seiko",
                "category_slug": "dive-watches",
                "movement": WatchMovement.AUTOMATIC,
                "case": "Stainless Steel",
                "strap": "Silicone",
                "water_resistance": "200m",
                "dial_color": "Matte Black",
                "price": Decimal("135000.00"),
                "stock": 8,
                "threshold": 3,
                "images": [
                    "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=800&q=80"
                ],
            },
            {
                "sku": "TISSOT-PRX-POWERMATIC",
                "name": "Tissot PRX Powermatic 80",
                "model": "T137.407.11.041.00",
                "description": (
                    "Slim retro 1970s integrated bracelet watch with the revolutionary "
                    "Powermatic 80 calibre with Nivachron hairspring."
                ),
                "brand_slug": "tissot",
                "category_slug": "sports-watches",
                "movement": WatchMovement.AUTOMATIC,
                "case": "Stainless Steel",
                "strap": "Stainless Steel",
                "water_resistance": "100m",
                "dial_color": "Sunburst Blue Waffle",
                "price": Decimal("245000.00"),
                "stock": 5,
                "threshold": 2,
                "images": [
                    "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=800&q=80"
                ],
            },
            {
                "sku": "ORIENT-BAMBINO-V4-GRN",
                "name": "Orient Bambino Version 4",
                "model": "FAC08002F0",
                "description": (
                    "Signature domed crystal with emerald green sunburst dial and "
                    "hacking/hand-winding caliber F6724."
                ),
                "brand_slug": "orient",
                "category_slug": "dress-watches",
                "movement": WatchMovement.AUTOMATIC,
                "case": "Stainless Steel",
                "strap": "Genuine Leather",
                "water_resistance": "30m",
                "dial_color": "Emerald Green",
                "price": Decimal("85000.00"),
                "stock": 12,
                "threshold": 4,
                "images": [
                    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=800&q=80"
                ],
            },
            {
                "sku": "CASIO-EDIFICE-OCTA",
                "name": "Casio Edifice EFR-S108D Slim Sapphire",
                "model": "EFR-S108D-2AV",
                "description": (
                    "Ultra-thin 7.8mm octagonal bezel sports timepiece equipped with "
                    "scratch-resistant sapphire crystal."
                ),
                "brand_slug": "casio",
                "category_slug": "chronographs",
                "movement": WatchMovement.QUARTZ,
                "case": "Stainless Steel",
                "strap": "Solid Stainless Steel",
                "water_resistance": "100m",
                "dial_color": "Turquoise Blue",
                "price": Decimal("48000.00"),
                "stock": 15,
                "threshold": 5,
                "images": [
                    "https://images.unsplash.com/photo-1533139502658-0198f920d8e8?auto=format&fit=crop&w=800&q=80"
                ],
            },
            {
                "sku": "CITIZEN-PROMASTER-ECO",
                "name": "Citizen Promaster Marine Eco-Drive",
                "model": "BN0150-28E",
                "description": (
                    "Solar light-powered diver watch that never needs battery change. "
                    "200m ISO compliant with anti-reflective crystal."
                ),
                "brand_slug": "citizen",
                "category_slug": "dive-watches",
                "movement": WatchMovement.QUARTZ,
                "case": "Stainless Steel",
                "strap": "Polyurethane",
                "water_resistance": "200m",
                "dial_color": "Deep Black",
                "price": Decimal("110000.00"),
                "stock": 4,
                "threshold": 3,
                "images": [
                    "https://images.unsplash.com/photo-1542496658-e33a6d0d50f6?auto=format&fit=crop&w=800&q=80"
                ],
            },
        ]

        for w in watches:
            p = session.execute(select(Product).where(Product.sku == w["sku"])).scalar_one_or_none()
            if not p:
                brand = brand_map[w["brand_slug"]]
                category = category_map[w["category_slug"]]
                p = Product(
                    sku=w["sku"],
                    name=w["name"],
                    model=w["model"],
                    description=w["description"],
                    brand_id=brand.id,
                    category_id=category.id,
                    movement_type=w["movement"],
                    case_material=w["case"],
                    strap_material=w["strap"],
                    water_resistance=w["water_resistance"],
                    dial_color=w["dial_color"],
                    image_urls=w["images"],
                    price_lkr=w["price"],
                    status=ProductStatus.PUBLISHED,
                    low_stock_threshold=w["threshold"],
                )
                session.add(p)
                session.flush()

                # Add stock & movement
                inv = InventoryItem(
                    product_id=p.id,
                    on_hand=w["stock"],
                    reserved=0,
                )
                session.add(inv)
                session.flush()

                movement = InventoryMovement(
                    product_id=p.id,
                    movement_type=InventoryMovementType.ADJUSTMENT,
                    quantity_delta=w["stock"],
                    reserved_delta=0,
                    on_hand_after=w["stock"],
                    reserved_after=0,
                    reason=AdjustmentReason.RESTOCK,
                    notes="Initial catalog seed",
                    actor_id=admin.id,
                )
                session.add(movement)
                print(f"Added product: {p.name} ({p.sku})")
            else:
                print(f"Product already exists: {p.name}")

        session.commit()
        print("\nSeed data successfully committed to database!")


if __name__ == "__main__":
    seed_database()
