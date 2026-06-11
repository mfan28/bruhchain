import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Cassandra
    CASSANDRA_HOST: str = os.getenv("CASSANDRA_HOST", "localhost")
    CASSANDRA_PORT: int = int(os.getenv("CASSANDRA_PORT", "9042"))
    CASSANDRA_KEYSPACE: str = os.getenv("CASSANDRA_KEYSPACE", "blockchain")

    # IPFS
    IPFS_HOST: str = os.getenv("IPFS_HOST", "localhost")
    IPFS_PORT: int = int(os.getenv("IPFS_PORT", "5001"))

    # IPFS Cluster
    CLUSTER_HOST: str = os.getenv("CLUSTER_HOST", "localhost")
    CLUSTER_PORT: int = int(os.getenv("CLUSTER_PORT", "9096"))

    # State DB (LevelDB)
    STATE_DB_PATH: str = os.getenv("STATE_DB_PATH", "/data/state.db")

    # Mining
    MINING_DIFFICULTY: int = int(os.getenv("MINING_DIFFICULTY", "5")) 
    MAX_TX_PER_BLOCK: int = int(os.getenv("MAX_TX_PER_BLOCK", "100"))
    BLOCK_REWARD_ADDRESS: str = os.getenv("BLOCK_REWARD_ADDRESS", "")

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # P2P / Node Identity
    NODE_ID: str = os.getenv("NODE_ID", "")
    NODE_HOST: str = os.getenv("NODE_HOST", "localhost")
    NODE_PORT: int = int(os.getenv("NODE_PORT", "8000"))
    SEED_PEERS: list[str] = [
        p.strip() for p in os.getenv("SEED_PEERS", "").split(",") if p.strip()
    ]


settings = Settings()