import sys
import pandas as pd
"""
Example usage: python 2024dataframe.py .\dataprocessing_tutee\Book11.xlsx .\dataprocessing_tutee\Book12.xlsx

Make sure change the following column names:
for tutor worksheet:
- Tutor First Name
- Tutor Last Name
- Tutor Subjects
- Tutor Gender
For tutee worksheet:
- Tutee 1 First Name
- Tutee 1 Last Name
- Tutee 1 Primary Subject
- Tutee 1 Secondary Subject
- Tutee 1 Tertiary Subject
- Gender Preference
"""

# Check that the user has provided the correct number of arguments
if len(sys.argv) != 3:
    print("Usage: python 2024dataframe.py <tutor_file.xlsx> <tutee_file.xlsx>")
    sys.exit(1)

# sys.argv[1] will be the tutor file (e.g., Book11.xlsx)
# sys.argv[2] will be the tutee file (e.g., Book12.xlsx)
tutor_file = sys.argv[1]
tutee_file = sys.argv[2]

# Step 1: Read the data from the Excel files passed as arguments
tutor_data = pd.read_excel(tutor_file)
tutor_data['Tutor Full Name'] = (tutor_data['Tutor First Name'].astype(str) +
                                 " " +
                                 tutor_data['Tutor Last Name'].astype(str))

tutee_data = pd.read_excel(tutee_file)
tutee_data['Tutee Full Name'] = (tutee_data['Tutee 1 First Name'].astype(str) +
                                 " " +
                                 tutee_data['Tutee 1 Last Name'].astype(str))

# Step 2: Make sure the length of tutee list is not longer than tutor list
n1 = len(tutor_data)
n2 = len(tutee_data)
if n1 < n2:
    tutee_data = tutee_data.head(n1)

# Define the subjects you want to count
subjects = [
    "English",
    "Social Sciences",
    "Math Grades 7, 8, 9, 10",
    "Functions (Grade 11)", # no need to delete the brackes
    # however, make sure to change regex to False
    "Calculus and/or Advanced Functions (Grade 12)",
    # make sure to change regex to False again
    "Science Grades 7, 8, 9, 10",
    "Biology",
    "Chemistry",
    "Physics",
    "French",
    "Computer",
    "Data",
    "History"
    # Add "Law" here if needed
]

# Count how many tutors can teach each subject directly using DataFrame operations
subject_counts = {}
for subj in subjects:
    subject_counts[subj] = tutor_data['Tutor Subjects'].str.contains(subj, na=False, regex=False).sum()
print("Subject counts:", subject_counts)
# Now compute the urgency score for each tutee directly from df2
# We'll store scores in a list and then add them to df2
urgency_scores = []

for _, row in tutee_data.iterrows():
    # Extract the subject preferences and gender preference
    primary_subj = row['Tutee 1 Primary Subject']
    secondary_subj = row['Tutee 1 Secondary Subject']
    tertiary_subj = row['Tutee 1 Tertiary Subject']
    gender_pref = row['Gender Preference']

    # Calculate the score for each tutee
    score = 0

    # Use a helper function to add points based on which subject the tutee needs
    def add_subject_score(tutee_subject, weight):
        for subj in subjects:
            if subj in str(tutee_subject):  # Check if the subject string is contained
                # Avoid division by zero if no tutors teach this subject
                if subject_counts[subj] > 0:
                    return weight * 100 / subject_counts[subj]
        return 0

    # Primary subject (weight = 10)
    score += add_subject_score(primary_subj, 10)

    # Secondary subject (weight = 3)
    score += add_subject_score(secondary_subj, 3)

    # Tertiary subject (weight = 1)
    score += add_subject_score(tertiary_subj, 1)

    # Gender preference bonus
    if gender_pref != "No preference":
        score += 1000

    score = round(score)
    urgency_scores.append(score)

# Add the scores to df2
tutee_data['URGENCY_SCORE'] = urgency_scores

# Next, you can match tutors to tutees using df1 and df2 directly.
# For example, you can sort df2 by URGENCY_SCORE to match the most urgent tutees first.
tutee_data = tutee_data.sort_values(by='URGENCY_SCORE', ascending=False)

# Now find best matching tutors for each tutee
# We'll need to loop over sorted df2 and pick tutors from df1
matched_rows = []
available_tutors = tutor_data.copy()

"""
This is the main loop that matches tutors to tutees.
It loops over each tutee and finds the best matching tutor.
For each tutee, it computes a matching score for each available tutor.
Then it picks the tutor with the highest score and stores the match.
After that it removes the matched tutor from the pool of available tutors.
"""
for i, tutee_row in tutee_data.iterrows():
    """
    # Uncomment this block to inspect the first few rows
    if i == 2:
        # Print values to inspect them
        print("Index i:", i)
        print("Row:", t_row)
        break
    """
    p_subj = str(tutee_row['Tutee 1 Primary Subject'])
    s_subj = str(tutee_row['Tutee 1 Secondary Subject'])
    t_subj = str(tutee_row['Tutee 1 Tertiary Subject'])
    g_pref = str(tutee_row['Gender Preference'])

    # Compute a matching score for each available tutor
    # Initialize the matching score column to zero for the next tutee
    available_tutors['MATCHING_PT'] = 0

    # Primary subject check
    available_tutors.loc[
        available_tutors['Tutor Subjects'].str.contains(p_subj, na=False, regex=False),
        'MATCHING_PT'
    ] += 1000000

    # Secondary subject check
    available_tutors.loc[
        available_tutors['Tutor Subjects'].str.contains(s_subj, na=False, regex=False),
        'MATCHING_PT'
    ] += 100

    # Tertiary subject check
    if pd.notna(t_subj) and t_subj.strip():
        available_tutors.loc[
            available_tutors['Tutor Subjects'].str.contains(t_subj, na=False, regex=False),
            'MATCHING_PT'
        ] += 1

    # Gender preference
    if g_pref == "Female":
        # Zero out non-Female tutors
        available_tutors.loc[available_tutors['Tutor Gender'] != "Female", 'MATCHING_PT'] = 0
    elif g_pref == "Male":
        # Zero out non-Male tutors
        available_tutors.loc[available_tutors['Tutor Gender'] != "Male", 'MATCHING_PT'] = 0

    # Pick the best tutor
    best_tutor_row = available_tutors.sort_values(by='MATCHING_PT', ascending=False).iloc[0]
    best_tutor_name = best_tutor_row['Tutor Full Name']
    best_tutor_score = best_tutor_row['MATCHING_PT']

    # Store the match
    matched_rows.append(
        pd.concat(
            [
                best_tutor_row.to_frame().T.reset_index(drop=True),
                tutee_row.to_frame().T.reset_index(drop=True)
            ],
            axis='columns'
        )
    )

    # Remove matched tutor from the pool
    available_tutors = available_tutors[available_tutors['Tutor Full Name'] != best_tutor_name]

# Concatenate all matched pairs
master = pd.concat(matched_rows, ignore_index=True)

# Add the MATCHING_SCORE column
master['MATCHING_SCORE'] = master['MATCHING_PT']
# remove the matching point column
master.drop(columns=['MATCHING_PT'], inplace=True)

master.to_excel('Master_dataframe.xlsx', index=False)
print("Successfully written to excel file using pandas")

# Save unmatched tutors to a separate Excel file
available_tutors.drop(columns=['MATCHING_PT'], inplace=True)
available_tutors.to_excel('un_matched_tutor.xlsx', index=False)