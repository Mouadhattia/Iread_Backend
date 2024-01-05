from neo4j import GraphDatabase
import spacy
import json

# Load the spaCy English model
nlp = spacy.load("en_core_web_sm")

class Neo4jDriver:
    """
    This class provides a simple interface for creating and managing Neo4j database connections.
    """
    DEFAULT_URI = "neo4j+ssc://01039f38.databases.neo4j.io"
    #DEFAULT_URI = "bolt://localhost:7687" 
    """The default URI to use when connecting to the Neo4j database."""
    DEFAULT_AUTH = ("neo4j", "ISLdTbysBGCHzydezsV_uc_gcUv_xsjK7PzzW0xpdfk")
    #DEFAULT_AUTH = ("neo4j", "0000")
    """The default auth tuple to use when connecting to the Neo4j database."""
    def __init__(self, uri=DEFAULT_URI, auth=DEFAULT_AUTH):
        """
        Initialize a new `Neo4jDriver` instance with the given connection parameters.
        Args:
            uri (str, optional): The URI to use when connecting to the Neo4j database. Defaults to `DEFAULT_URI`.
            auth (tuple, optional): The auth tuple to use when connecting to the Neo4j database. Defaults to `DEFAULT_AUTH`.
        """
        self.uri = uri
        self.auth = auth
        #self.driver = self.get_driver()
  
    def get_driver(self):
        """
        Create a new driver for the Neo4j database using the given connection parameters.
        Args:
            uri (str): The URI to use when connecting to the Neo4j database.
            auth (tuple): The auth tuple to use when connecting to the Neo4j database.
        Returns:
            Neo4j.BoltDriver: A new Neo4j driver instance.
        """
        driver = None 
        try:
            driver = GraphDatabase.driver(uri=self.uri, auth=self.auth)
        except Exception as e:
            print(f"Error connecting to Neo4j: {e}")
        return driver

    def close(self, driver):
        """
        Close the current Neo4j database connection.
        """
        try:
            self.driver.close()
        except Exception as e:
            print(f"Error closing Neo4j driver: {e}")

    def run(self, query, params=None):
        """
        Run a query on the Neo4j database and return the results.

        Args:
            query (str): The query to run on the Neo4j database.
            params (dict, optional): The parameters to use in the query. Defaults to None.

        Returns:
            Neo4j.RecordList: A list of results returned by the query.
        """
        with self.driver.session() as session:
            result = session.run(query, params)
            return result

class DataSetDB:
    """
    Class to handle DataSet-related operations with the Neo4j database
    """
    
    
    #def add_word(driver, headword: str, cefr: str ,pos: str, CoreInventory_1: str, CoreInventory_2: str, Threshold: str) -> None:
    @staticmethod
    def add_word(driver, headword: str, cefr: str ,pos: str, lemma: str) -> None:
        """
        Add a word to the Neo4j database
        :return: None
        """
        pos_dic = {"adverb": "ADV",
                   "adjective":"ADJ",
                   "noun":"NOUN",
                   "verb":"VERB"
                   }
        if pos_dic.get(pos) is not None:
            pos= pos_dic[pos]
        try:
            with driver.session() as session:
                # Check if the CEFR node already exists
                result = session.run("MATCH (c:CEFR {level: $cefr}) "
                                    "RETURN c", cefr=cefr)
                if result.single() is None:
                    # Create the CEFR node if it doesn't exist
                    session.run("CREATE (c:CEFR {level: $cefr})", cefr=cefr)
                
                result = session.run("MATCH (p:POS {name: $pos}) "
                                    "RETURN p", pos=pos)
                if result.single() is None:
                    # Create the POS node if it doesn't exist
                    session.run("CREATE (p:POS {name: $pos})", pos=pos)
                
                # Create a new word node in the database and relate it to the CEFR node
                session.run("MATCH (c:CEFR {level: $cefr}) "
                            "MATCH (p:POS {name: $pos}) "
                            "CREATE (w:Word {word: $headword}) "
                            "CREATE (w)-[:LEVEL{name: $pos}]->(c) "
                            "CREATE (w)-[:POS{level: $cefr}]->(p) "
                            "SET w.pos = $pos "
                            "SET w.length = $word_length "
                            "SET w.lemma = $lemma ", 
                            headword=headword, pos=pos, cefr=cefr, word_length=len(headword),
                            lemma =lemma)
            #print("Word added successfully!")
        except Exception as e:
            print(f"Error adding word: {e}")
    
    @staticmethod
    def check_word_in_db(driver, headword):
        try:
            with driver.session() as session:
                # Check if the headword node already exists
                result = session.run("MATCH (c:Word {word: $headword}) "
                                    "RETURN c LIMIT 1", headword=headword)
                                    
                if result.single() is None:
                    # Create the CEFR node if it doesn't exist
                    print(headword, ":  No ")
                else:
                    print("Yes")
        except Exception as e:
            print(f"Error adding word: {e}")

    @staticmethod
    def get_word_from_db(driver, word):
        lemma_list = nlp(word)
        if len(lemma_list) > 0:
            lemma = lemma_list[0].lemma_
        else:
          
            return {'message': f"We coudnt extact the lemma from: {word}",'code':400}
        try:
            with driver.session() as session:
                # Check if the headword node already exists
                result = session.run("MATCH (c:Word {lemma: $lemma}) -[:LEVEL]->(level) "
                                    "RETURN c, level LIMIT 1", lemma=lemma)
                record = result.single()               
                if record is None:
                    # Create the Word node if it doesn't exist
                    return {'message': f"No nodes found for lemma: {lemma}",'code':400}
                else:
                    response_message = "Yes"
                    c_node = dict(record['c'])
                    level_node = dict(record['level'])
                    # Create the result dictionary
                    result_dict = {'c': c_node, 'level': level_node}
                    # return jsonify({'result': result_dict})
                # return json.dumps({'message': response_message})
                return result_dict
        except Exception as e:
            
            return json.dumps({'error': str(e)})

    @staticmethod
    def add_relationship_Book_word_in_db(driver, title : str, headword :  list, headwords_dic: dict):
        #create a file to save the non found headwords into the db
        #We will add every non found word into this file to be processed 
        #by an English expert 
        file_headwords = "non_found_headwords.txt"
        try:
            with driver.session() as session:
                # Check if the word node already exists
                result = session.run("create (b:Book {title: $title}) "
                                    "RETURN b", title=title)
                record = result.single()
                book_id = record["b"].id
                for h_w in headword:
                    result = session.run("MATCH (w:Word {headword: $h_w}) "
                                        "RETURN w", h_w=h_w)
                    record = result.single()
                    if record is None:
                        with open(file_headwords, "a") as file:
                            file.write(f"{book_id}; {h_w}; {headwords_dic[h_w]}\n")
                    else:
                        word_id = record["w"].id
                        session.run("MATCH (b) WHERE ID(b) = $book_id "
                                    "MATCH (w) WHERE ID(w) = $word_id "
                                    "CREATE (b)-[:HAS_WORD]->(w)",
                                    book_id=book_id, word_id=word_id)
        except Exception as e:
            print(f"Error adding word: {e}")