import csv
from Datasets.db import DataSetDB, Neo4jDriver
import nltk
from nltk import word_tokenize, pos_tag
#nltk.download('punkt')
#nltk.download('wordnet')
from nltk.corpus import wordnet
from nltk.tokenize import word_tokenize
import logging
import tqdm
import spacy

# Load the spaCy English model
nlp = spacy.load("en_core_web_sm")


logging.basicConfig(filename="create_cefr_db.log", level=logging.DEBUG)
log = logging.getLogger(__name__)



def parse_csv(file_path):
    """
    Parse a CSV file and return its data and column names.
    
    Args:
        file_path (str): The path to the CSV file.
    
    Returns:
        tuple: A tuple containing the data as a list of dictionaries and the column names as a list of strings.
    """
    # Initialize an empty list to store the data
    data = []
    # Initialize an empty list to store the column names
    column_names = []
    # Open the CSV file
    with open(file_path, 'r', encoding='utf-8') as file:
        # Create a DictReader object to read the file
        reader = csv.DictReader(file)
        # Get the column names from the DictReader object
        column_names = reader.fieldnames
        # Loop over each row in the file and append the row as a dictionary to the data list
        for row in reader:
            data.append(row)
            #print(row)
            #h_w =row["headword"]
            #categories = categorize_word(h_w)
            #input (f"{h_w}:  {categories}")
    # Return the data and column names
    print(column_names)
    return data, column_names

def create_cefr_db(file_path):
    """
    Create a CEFR (Common European Framework of Reference for Languages) database.
    """
    
    log = logging.getLogger(__name__)
    log.debug("Parsing CSV file: %s", file_path)
    data, column_names = parse_csv(file_path)
    log.debug("CSV file parsed successfully")
    log.debug("Getting an instance of the Neo4jDriver")
    driver = Neo4jDriver().get_driver()
    log.debug("Instance of Neo4jDriver created successfully")
    # Loop over each row in the data, using tqdm to display a progress bar
    log.debug("Adding data to the database")
    for row in tqdm.tqdm(data, desc="File..."):
        # Add the word to the database
        lemma_list = nlp(row["headword"])
        if len(lemma_list) > 0:
            lemma = lemma_list[0].lemma_
        else:
            lemma = ""
        DataSetDB.add_word(driver, row["headword"], row["CEFR"],row["pos"], lemma)
        log.debug("Word added to the database successfully: %s", row["headword"])
    log.debug("Closing the instance of the Neo4jDriver")
    driver.close()
    log.debug("Instance of Neo4jDriver closed successfully")

#This function id=s used to when parsing books
def get_headwords(text):
    headwords = []
    headwords_dic={}
    words = word_tokenize(text)
    for word in words:
        headword = wordnet.morphy(word)
        #print(f"{word}: {headword}")
        headwords.append(headword)
        headwords_dic[headword] = word
    return headwords, headwords_dic

def categorize_word(word):
    synsets = wordnet.synsets(word)
    if len(synsets) == 0:
        return None
    hypernyms = []
    for synset in synsets:
        hypernyms.extend([hypernym.lemma_names()[0] for hypernym in synset.hypernyms()])
    return hypernyms

def main_create_cefr_db():
    create_cefr_db('./Datasets/olp-en-cefrj-master/cefrj-vocabulary-profile-1.5.csv')
    #input("Next file")
    create_cefr_db('./Datasets/olp-en-cefrj-master/octanove-vocabulary-profile-c1c2-1.0.csv')
if __name__=="__main__":
    main_create_cefr_db()