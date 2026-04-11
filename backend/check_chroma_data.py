import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
try:
    c = client.get_collection('sap_master_schemas')
    print('Schema Collection Count:', c.count())
    results = c.peek()
    print('Sample IDs:', results['ids'])
except Exception as e:
    print('Error:', e)
