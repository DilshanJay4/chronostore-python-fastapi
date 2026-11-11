"""User profile and address management service."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import BusinessRuleViolationError, NotFoundError
from app.models.entities import Address, User
from app.schemas.users import AddressCreate, AddressUpdate, UserProfileUpdate


class UserService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def update_profile(self, user: User, data: UserProfileUpdate) -> User:
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.phone is not None:
            user.phone = data.phone
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_addresses(self, user_id: uuid.UUID) -> list[Address]:
        return list(
            self.session.execute(
                select(Address)
                .where(Address.user_id == user_id)
                .order_by(Address.is_default.desc(), Address.created_at.desc())
            )
            .scalars()
            .all()
        )

    def add_address(self, user_id: uuid.UUID, data: AddressCreate) -> Address:
        count = (
            self.session.execute(select(Address).where(Address.user_id == user_id)).scalars().all()
        )
        if len(count) >= self.settings.max_addresses_per_user:
            raise BusinessRuleViolationError(
                f"Maximum of {self.settings.max_addresses_per_user} addresses allowed."
            )

        # If this is the first address, or marked default, handle default flag
        is_default = data.is_default or len(count) == 0
        if is_default:
            self.session.execute(
                update(Address).where(Address.user_id == user_id).values(is_default=False)
            )

        address = Address(
            user_id=user_id,
            label=data.label,
            recipient_name=data.recipient_name,
            phone=data.phone,
            street_line1=data.street_line1,
            street_line2=data.street_line2,
            city=data.city,
            postal_code=data.postal_code,
            province=data.province,
            country_code=data.country_code,
            is_default=is_default,
        )
        self.session.add(address)
        self.session.commit()
        self.session.refresh(address)
        return address

    def update_address(
        self, user_id: uuid.UUID, address_id: uuid.UUID, data: AddressUpdate
    ) -> Address:
        address = self.session.execute(
            select(Address).where(Address.id == address_id, Address.user_id == user_id)
        ).scalar_one_or_none()
        if not address:
            raise NotFoundError("Address not found.")

        if data.is_default is True:
            self.session.execute(
                update(Address).where(Address.user_id == user_id).values(is_default=False)
            )
            address.is_default = True

        for field, value in data.model_dump(exclude_unset=True).items():
            if field != "is_default":
                setattr(address, field, value)

        self.session.commit()
        self.session.refresh(address)
        return address

    def delete_address(self, user_id: uuid.UUID, address_id: uuid.UUID) -> None:
        address = self.session.execute(
            select(Address).where(Address.id == address_id, Address.user_id == user_id)
        ).scalar_one_or_none()
        if not address:
            raise NotFoundError("Address not found.")

        was_default = address.is_default
        self.session.delete(address)
        self.session.flush()

        if was_default:
            # Promote another address to default if available
            next_addr = (
                self.session.execute(
                    select(Address)
                    .where(Address.user_id == user_id)
                    .order_by(Address.created_at.desc())
                )
                .scalars()
                .first()
            )
            if next_addr:
                next_addr.is_default = True

        self.session.commit()
