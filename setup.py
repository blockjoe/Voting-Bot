from setuptools import setup, find_packages

setup(
    name="Voting-Bot",
    version="0.0.1",
    packages=find_packages(),
    install_requires=[
        "python-dotenv>=0.20.0",
        "sqlalchemy>=1.4.37",
        "fastapi[all]>=0.78.0",
        "discord>=1.7.3",
        "wheel",
    ],
    entry_points={"console_scripts": ["run-discord=bot.bot:main"]},
)
