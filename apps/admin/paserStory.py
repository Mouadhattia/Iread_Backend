import spacy

# Load the spaCy English model
nlp = spacy.load("en_core_web_sm")


def get_tenses_words(text):
    # Process the text with spaCy
    doc = nlp(text)

    words = []

    for token in doc:
        if token.pos_ == "VERB" or token.tag_ == "MD" or (token.pos_ == "AUX" and token.dep_ == "aux"):
            # Extract relevant information
            word = token.text
            lemma = token.lemma_
            pos = token.pos_
            tag = token.tag_

            # Initialize tense as Unknown
            tense = "Unknown"

            # Define tense categories based on POS tags and lemmatization
            if tag == "VBD":  # Past tense
                tense = "Simple Past"
            elif tag == "VBZ":  # Present tense
                tense = "Simple Present"
            elif tag == "VBP" and token.i + 1 < len(doc) and doc[token.i + 1].tag_ == "VBG":
                tense = "Present Continuous"
            elif tag == "VBN" and token.i - 1 >= 0 and doc[token.i - 1].tag_ == "MD":
                tense = "Future Perfect"
            elif tag == "VBD" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "had":
                tense = "Past Perfect"
            elif tag == "VBG" and token.i - 1 >= 0 and (doc[token.i - 1].tag_ == "MD" or doc[token.i - 1].tag_ == "VBD"):
                tense = "Past Continuous"
            elif tag == "VBG" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "will":
                tense = "Future Continuous"
            elif tag == "VBG" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "had":
                tense = "Past Perfect Continuous"
            elif tag == "VBG" and token.i - 1 >= 0 and doc[token.i - 1].tag_ == "VBN":
                tense = "Present Perfect Continuous"
            elif tag == "VBN" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "will":
                tense = "Future Perfect Continuous"
            elif tag == "VBN" and token.i - 1 >= 0 and doc[token.i - 1].tag_ == "VBG":
                tense = "Present Perfect Continuous"
            elif tag == "VB" and token.i - 1 >= 0 and doc[token.i - 1].tag_ == "MD":
                tense = "Future Simple"
            elif tag == "VB" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "will":
                tense = "Future Simple"
            elif tag == "VBP" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "will":
                tense = "Future Simple"
            elif tag == "VBP" and token.i - 1 >= 0 and doc[token.i - 1].tag_ == "VBN":
                tense = "Future Perfect Continuous"
            elif tag == "VBP" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "had":
                tense = "Past Perfect Continuous"
            elif tag == "VBP" and token.i - 1 >= 0 and doc[token.i - 1].tag_ == "VBG":
                tense = "Present Perfect Continuous"
            elif tag == "VBP" and token.i - 1 >= 0 and doc[token.i - 1].text.lower() == "have":
                tense = "Present Perfect Continuous"
            # Additional logic for other tenses could be added here

            words.append({"word": word, "lemma": lemma, "pos": pos, "tag": tag, "tense": tense})
            #print({"word": word, "lemma": lemma, "pos": pos, "tag": tag, "tense": tense})
        else:
            word = token.text
            lemma = token.lemma_
            pos = token.pos_
            tag = token.tag_
            words.append({"word": word, "lemma": lemma, "pos": pos, "tag": tag})
    return  words

def main():

    text ="Yesterday, I had a wonderful day at the park with my friends. It was a sunny day, and the weather was perfect for outdoor activities. We decided to have a picnic and enjoy some games. In the morning, we gathered at the park with our picnic baskets filled with sandwiches, fruits, and snacks. We found a nice spot under a big tree and spread out a blanket. As we sat down to eat, we chatted and laughed, sharing stories about our week."
    words  =get_tenses_words(text)
    for word in words:
        print(word ,"\n")
        

 
if __name__=="__main__":
    main()

    