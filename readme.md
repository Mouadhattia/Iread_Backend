# English Reading Platform

The English Reading Platform is a comprehensive web application designed to help users improve their English language skills through reading and interactive learning. The platform offers a wide range of features that cater to users of different language proficiency levels, making language learning engaging and enjoyable.

## Features

- **Word Dataset**: Access an extensive dataset of English words for quick and efficient word searches.
- **Customized Reading**: Choose from a diverse collection of books tailored to your English language level, whether you're a beginner, intermediate, or advanced learner.
- **Live Reading Sessions**: Participate in real-time online reading sessions, where you can read along with others and discuss the content.
- **Collaborative Study**: Engage in collaborative book studies led by a session master or alongside fellow users. Explore themes, analyze content, and enhance comprehension together.
- **Interactive Quizzes**: After completing a book, test your understanding with interactive quizzes that reinforce your learning.
- **Progression Levels**: Work through objectives specific to your level, and advance to higher levels as you complete the assigned goals.
- **CEFR-based Recommendations**: Receive book recommendations based on the Common European Framework of Reference (CEFR) for Languages, ensuring appropriate challenges for every stage of your language journey.

## Getting Started

### Prerequisites

Before you begin, ensure you have the following prerequisites:

- **Python (3.6 or higher)**: If you don't have Python installed, you can download it from the official Python website:
  [https://www.python.org/downloads/](https://www.python.org/downloads/).

- **Flask**: Flask is a micro web framework for Python.

- **MySQL**: MySQL is a relational database management system. Download and install MySQL from the official website:
  [https://www.mysql.com/products/workbench/](https://www.mysql.com/products/workbench/). Follow the installation steps provided.

- **Text Editor**: You will need a text editor to work on your project. We recommend downloading Visual Studio Code from the official website: [https://code.visualstudio.com/](https://code.visualstudio.com/).

If you're new to any of these technologies, you might find the official documentation and online tutorials helpful to get started.

- **Gmail Account with Two-Factor Authentication**: For email sending functionality, you will need a Gmail account with two-factor authentication enabled. You will also need to create an application password for the English Reading Platform.

- **Postman**: Postman is a powerful tool used for testing and interacting with APIs (Application Programming Interfaces). It provides a user-friendly interface that allows you to send various types of HTTP requests to backend endpoints for testing and debugging purposes. To use Postman:

  1. **Download Postman**: You can download Postman from the official website: [https://www.postman.com/](https://www.postman.com/). Choose the version compatible with your operating system.
  2. **Install Postman**: Follow the installation instructions for your operating system after downloading.
  3. **Open Postman**: Once installed, open Postman. You'll be greeted with a user-friendly interface.
  4. **Create Requests**: Choose an HTTP request method (GET, POST, PUT, DELETE, etc.), enter the URL of the backend endpoint, add headers, query parameters, or request body data if needed.
  5. **Send Requests**: Click the "Send" button to send the request. Postman will display the backend's response, including status codes, headers, and response body.
  6. **Organize and Save**: You can save requests and group them into collections for better organization.

  Postman is an essential tool for developers working with APIs, as it streamlines the process of testing and debugging backend functionality. For further guidance, refer to the official Postman documentation or online tutorials.

These prerequisites ensure that you have the necessary tools and software to set up and run the English Reading Platform. Once you have these installed, you can proceed with the installation and configuration steps outlined in the next sections.

### Installation

1. **Clone the Repository**:

   - If you don't have Git installed on your system, you can download and install it from the official Git website: [https://git-scm.com/downloads](https://git-scm.com/downloads).
   - Open your Terminal or Command Prompt.
   - To clone the repository, navigate to the directory where you want to store it and run the following command:
     ```
     git clone https://github.com/jeanChretienKouete/IntellectEnglish.git
     ```
     This command will create a new folder with the repository name and download all the files from the repository into that folder.
   - Access the Cloned Repository: Navigate into the newly created directory:
     ```
     cd IntellectEnglish
     ```
   - Switch to the `master` branch by executing:
     ```
     git checkout master
     ```
   - You now have a local copy of the repository on your machine ready for further steps.

2. **Set Up and Activate a Virtual Environment**:

   - Open your command prompt (cmd).
   - Navigate to the "backend" folder of your project:
     ```
     cd backend
     ```
   - Create a virtual environment (env) named "venv" or "env" based on your platform:
     - On Windows:
       ```
       py -3 -m venv venv
       ```
     - On Linux/macOS:
       ```
       python3 -m venv venv
       ```
   - Activate the virtual environment:
     - On Windows:
       ```
       venv\Scripts\activate
       ```
     - On Linux/macOS:
       ```
       source venv/bin/activate
       ```
   - Your command prompt will change to show the name of the activated environment.

3. **Install Required Packages**:

   - Within the activated environment, install the required packages by running the following command:
     ```
     pip install -r requirements.txt
     ```
   - This command will install all the necessary dependencies needed to run the project.

4. **Configure the MySQL Database**:

   - Open the `config.py` file in the root directory of your project.
   - Configure the database settings with your specific information:
     ```python
     SQLALCHEMY_DATABASE_URI = 'mysql://root:database_password@localhost/your_database_name'
     SECRET_KEY = os.environ.get('SECRET_KEY') or 'yourpassword'
     SQLALCHEMY_TRACK_MODIFICATIONS = True
     ```

   With these steps completed, your English Reading Platform is now set up and ready to be launched. The virtual environment ensures a clean and isolated environment for running your application, and the required packages are installed to fulfill the project's dependencies.

5. **Configure SMTP for Email Sending**:

   In order to enable email sending functionality, you need to configure the SMTP settings for your Gmail account. This will allow the English Reading Platform to send emails for various purposes, such as account notifications and communication. Follow the steps below to set up SMTP and generate an application password:

   a. Open the `config.py` file in your project directory.

   b. Locate the following lines and replace them with your Gmail credentials. Make sure to keep your credentials confidential:

   ```python
   MAIL_USERNAME = 'youremail@gmail.com'
   MAIL_PASSWORD = 'your_application_password'
   ```

   c. **Generate an Application Password for Secure Access**:

   An application password is a unique password generated by Google that enables you to securely use non-Google applications, like the English Reading Platform, with your Gmail account. Here's how you can generate an application password:

   - Step 1: Sign in to your Google Account.

   - Step 2: Go to the "Security" section, and under "Signing in to Google," click on "App passwords." Please ensure that you have activated Two-Factor Authentication before finding this option.

   - Step 3: You might need to re-enter your password. Once done, under the "Select app" dropdown, choose "Other (custom name)."

   - Step 4: Enter a descriptive name for the application, such as "English Reading Platform."

   - Step 5: Click the "Generate" button.

   - Step 6: Google will provide you with a unique 16-digit password for the application. Be sure to copy this password as you will need it to configure the SMTP settings.

   **Important Note**: Keep your generated application password secure and do not share it with anyone. While you won't be able to view the password again, you can generate a new one if required.

6. **Database Migration using Flask-Migrate**:

   To create all tables defined in the `models` folder in your database, you'll use Flask-Migrate, a powerful tool for managing database schema changes. Follow these steps:

   a. **Initialize Migrations**:

   - Open your terminal/command prompt and navigate to your project directory.
   - Run the following command to initialize migrations, which will add a `migrations` folder to your application:
     ```
     flask db init
     ```

   b. **Generate Initial Migration**:

   - After initializing migrations, create an initial migration to capture the current state of your models.
   - Run the following command, replacing `"Initial migration."` with a brief description of your changes:
     ```
     flask db migrate -m "Initial migration."
     ```
     This command generates an initial migration script based on the changes in your `models` folder.

   c. **Apply Migrations**:

   - Once the initial migration is generated, apply the changes to your database.
   - Run the following command to execute the migration script and update your database schema:
     ```
     flask db upgrade
     ```
     This command applies the changes described in the migration script to your database, creating the necessary tables.

   **Note**: Whenever you make changes to your models (add, modify, or delete), you will need to repeat steps b and c to update your database schema.

   Flask-Migrate ensures that your database structure stays synchronized with your application's models. Always review the generated migration script before applying it to your database to ensure data integrity and consistency.

## Usage

1. **Navigate to the project directory and run the Flask server**:

   - Open your terminal/command prompt and make sure you are in your project directory.
   - To start the Flask server, run the following command:
     ```
     flask run
     ```
   - You can activate the debug option by executing:
     ```
     flask run --debug
     ```
   - To specify a different port (e.g., port 3001), use:

     ```
     flask run --debug --port 3001


     ```

   - The default port used by Flask is 5000.

2. **Access the web application**:

   - Open your web browser and enter the following URL: `http://localhost:5000` (or the port you specified).
   - Create an account to get started with the English Reading Platform.

3. **Explore the features**:

   - Utilize the word search to quickly find English words from the extensive dataset.
   - Select a book tailored to your English language level and begin reading.
   - Join an ongoing live reading session to read and discuss content with others.

4. **Engage in collaborative learning**:

   - Participate in collaborative book studies led by a session master or fellow users.
   - Analyze content, explore themes, and enhance comprehension through discussions.
   - After reading a book, test your understanding with interactive quizzes.

5. **Track your progress**:
   - Monitor your language learning progress as you complete objectives and advance through levels.
   - Receive book recommendations based on the Common European Framework of Reference (CEFR) for Languages.

Remember to keep the Flask server running as you interact with the web application. You can stop the server at any time by pressing `Ctrl + C` in the terminal.

## Contributing

We welcome contributions from the community! To contribute:

1. Fork the repository and create a new branch.
2. Make your enhancements and ensure code quality.
3. Submit a pull request, describing the changes and their purpose.

## License

This project is licensed under the [MIT License](LICENSE).

## Contact

For questions or support, please email us at teamintellect@gmail.com.

## deploy

run server
nohup python app.py > app.log 2>&1 &

stop server
ps aux | grep "python app.py"
