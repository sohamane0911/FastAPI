from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, status
from pydantic import BaseModel, EmailStr, ConfigDict

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

from sqlalchemy import String, Text, select, DateTime, func, ForeignKey, Boolean
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from dotenv import load_dotenv
from imagekitio import ImageKit
import os

from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pwdlib import PasswordHash
import jwt

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-security-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

imagekit = ImageKit(
    private_key=os.getenv("IMAGEKIT_PRIVATE_KEY")
)

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl= "login")

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key= True, autoincrement= True)
    username: Mapped[str] = mapped_column(String(50), unique= True, index= True, nullable= False)
    email: Mapped[str] = mapped_column(String(60), unique= True, index= True, nullable= False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable= False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone= True), server_default=func.now(), nullable= False)

    posts: Mapped[list["PostModel"]] = relationship(
        back_populates= "owner", cascade= "all, delete-orphan",
    )

class PostModel(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    caption: Mapped[str] = mapped_column(String(150), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_name: Mapped[str] = mapped_column(String(150), nullable=False)
    file_id: Mapped[str] = mapped_column(String(200), nullable= False)
    is_public: Mapped[bool] = mapped_column(Boolean, default= True, nullable= False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete= "CASCADE"), nullable= False)
    owner: Mapped["UserModel"] = relationship(back_populates= "posts")

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class PostSchema(BaseModel):
    id: int
    caption: str
    url: str
    file_type: str
    file_name: str
    file_id: str
    is_public: bool
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

app = FastAPI()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire =datetime.now(timezone.utc) + (expires_delta or timedelta(minutes= 15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_users(
        token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> UserModel:
    credentials_exception = HTTPException(
        status_code= status.HTTP_401_UNAUTHORIZED,
        detail= "Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms= [ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

    except jwt.PyJWTError:
        raise credentials_exception

    result = await db.execute(select(UserModel).where(UserModel.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user

@app.post("/register", response_model= UserResponse)
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(UserModel).where(
            (UserModel.username == user_data.username) | (UserModel.email == user_data.email)
        )
    )

    if existing.scalar_one_or_none():
        raise HTTPException(status_code= 400, detail= "Username or email already registered")

    new_user = UserModel(
        username= user_data.username,
        email= user_data.email,
        hashed_password= password_hash.hash(user_data.password)
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@app.post("/login", response_model= Token)
async def login(
        form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserModel).where(UserModel.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not password_hash.verify(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data= {"sub": user.username}, expires_delta= timedelta(minutes= ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/upload", response_model= PostSchema)
async def upload_file(
    file: UploadFile = File(...),
    caption: str = Form(""),
    is_public: bool = Form(True),
    current_user: UserModel = Depends(get_current_users),
    db: AsyncSession = Depends(get_db)
):

    file_name = file.filename or "Unnamed file"
    file_bytes = await file.read()

    content_type = file.content_type
    if not content_type:
        content_type = "mp4/video" if file_name.endswith((".mp4", ".mov", ".avi", ".webm")) else "image/jpeg"

    try:
        upload_response = imagekit.files.upload(
            file= file_bytes,
            file_name= file_name,
            folder= "/insta_posts"
        )

        image_url = upload_response.url
        file_id = upload_response.file_id

    except Exception as e:
        raise HTTPException(status_code= 500, detail= f"Image upload failed: {str(e)}")

    post = PostModel(
        caption = caption,
        url = str(image_url),
        file_type = content_type,
        file_name = file_name,
        file_id = str(file_id),
        is_public = is_public,
        user_id = current_user.id
    )

    db.add(post)
    await db.commit()
    await db.refresh(post)

    return post

@app.get("/feed")
async def get_feed(
        limit: int = 10,
        offset: int = 0,
        db: AsyncSession = Depends(get_db)
):

    result = await db.execute(
        select(PostModel)
        .where(PostModel.is_public == True)
        .order_by(PostModel.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    post = result.scalars().all()
    return post

@app.get("/users/{username}/posts")
async def get_users_posts(username: str, db: AsyncSession = Depends(get_db)):
    user_res = await db.execute(select(UserModel).where(UserModel.username == username))
    target_user = user_res.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code= 404, detail= "User not found")

    result = await db.execute(
        select(PostModel)
        .where(PostModel.user_id == target_user.id)
        .where(PostModel.is_public == True)
        .order_by(PostModel.created_at.desc())
    )

    return result.scalars().all()

@app.delete("/delete_post/{post_id}")
async def delete_post_by_id(
    post_id: int,
    current_user: UserModel = Depends(get_current_users),
    db: AsyncSession = Depends(get_db)
):
    statement = select(PostModel).where(PostModel.id == post_id)
    result = await db.execute(statement)
    post = result.scalar_one_or_none()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.user_id != current_user.id:
        raise HTTPException(status_code= 404, detail= "You are not authorized to delete this post")

    if post.file_id:
        try:
            imagekit.files.delete(post.file_id)
        except Exception as e:
            print(f"Warning: ImageKit deletion skipped: {str(e)}")

    await db.delete(post)
    await db.commit()

    return {"message": f"Photo with post id {post_id} deleted successfully"}
