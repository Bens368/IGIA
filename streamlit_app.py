import streamlit as st
import fitz  # PyMuPDF
import base64
import requests
import pandas as pd
import os

# Fonction pour obtenir la liste triée des fichiers PDF en fonction des critères de l'utilisateur
def get_sorted_pdf_paths(uploaded_files):
    if not uploaded_files:
        st.error("No files uploaded.")
        return []

    pdf_files = [f for f in uploaded_files if 'IGA' in f.name and f.name.endswith('.pdf')]
    radar_files = sorted([f for f in pdf_files if 'raddar' in f.name], key=lambda x: x.name)
    w_files = sorted([f for f in pdf_files if 'W' in f.name], key=lambda x: x.name)
    other_files = sorted([f for f in pdf_files if f not in radar_files and f not in w_files], key=lambda x: x.name)

    return radar_files + w_files + other_files

# Fonction pour convertir chaque page d'un PDF en JPG
def convert_pdf_to_jpg(pdf_file, file_index, image_paths, output_directory):
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
    base_name = pdf_file.name.replace('.pdf', '')
    page = pdf_document.load_page(0)
    pix = page.get_pixmap()
    output_path = os.path.join(output_directory, f"{base_name}_page_{file_index + 1:02d}.jpg")
    pix.save(output_path)
    image_paths.append(output_path)

# Fonction pour encoder une image en base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# Application Streamlit
def main():
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #09308E;
            color: white;
        }
        .header {
            background-color: white;
            color: white;
            padding: 10px;
            display: flex;
            align-items: center;
        }
        .title-text {
            color: #E2AB49;
            font-size: 2em;
            font-weight: bold;
        }
        .stProgress > div > div > div > div {
            background-color: #E2AB49;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<h1 class="title-text">IGIA</h1>', unsafe_allow_html=True)

    # Demander la clé API
    api_key = st.text_input("OpenAI API Key", type="password")

    if not api_key:
        st.warning("Please provide an OpenAI API Key.")
        return

    # Espace de glisser-déposer pour les fichiers PDF
    uploaded_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)

    if uploaded_files:
        # Obtenir la liste triée des fichiers PDF
        sorted_files = get_sorted_pdf_paths(uploaded_files)
        total_files = len(sorted_files)

        if total_files == 0:
            st.write("No PDF files found.")
            return

        # Initialiser la liste pour stocker les chemins des images
        image_paths = []

        # Initialiser la barre de progression pour la conversion PDF en JPG
        # pdf_progress_bar = st.progress(0)

        # Convertir chaque PDF et suivre l'index de page global
        output_directory = "converted_files"  # Répertoire de sortie
        for index, pdf_file in enumerate(sorted_files):
            convert_pdf_to_jpg(pdf_file, index, image_paths, output_directory)
            # Mettre à jour la progression
            # pdf_progress_bar.progress((index + 1) / total_files)

        # Vérifier que tous les fichiers existent
        existing_paths = [path for path in image_paths if os.path.exists(path)]
        missing_paths = set(image_paths) - set(existing_paths)

        if missing_paths:
            st.write("Missing files:", missing_paths)
        else:
            st.write("All files generated successfully.")
            st.session_state.image_paths = existing_paths

    if 'image_paths' in st.session_state and st.session_state.image_paths:
        if st.button("Generate DataFrames"):
            # Liste pour stocker les DataFrames
            dataframes = []
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            # Initialiser la barre de progression pour les requêtes GPT-4
            gpt_progress_bar = st.progress(0)
            total_images = len(st.session_state.image_paths)

            for i, image_path in enumerate(st.session_state.image_paths):
                # Encoder l'image
                base64_image = encode_image(image_path)

                payload = {
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Transforme les ingrédients alimentaires dans cette image et leur prix en dataframe à deux colonnes. Genere moi uniquement le code python de l'objet dataframe qui se nommera data{i+1}, rien d'autre. La colonne des ingrédients se nommera Ingrédients et la colonne des prix se nommera Prix."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 4096
                }

                response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                response_json = response.json()

                # Extraire le texte du code de la réponse
                code_text = response_json['choices'][0]['message']['content']

                # Nettoyer le texte pour enlever les délimiteurs de code Markdown
                code_text = code_text.strip("```python").strip("```").strip()

                try:
                    # Exécuter le code extrait dans un environnement sûr
                    local_vars = {}
                    exec(code_text, {}, local_vars)
                    
                    # Vérifier que le DataFrame est créé et ajouter à la liste des DataFrames
                    dataframe = local_vars[f"data{i+1}"]
                    
                    if not isinstance(dataframe, pd.DataFrame):
                        raise ValueError(f"Le code généré n'a pas créé de DataFrame pour data{i+1}")
                    
                    if len(dataframe['Ingrédients']) != len(dataframe['Prix']):
                        raise ValueError(f"Les colonnes du DataFrame data{i+1} n'ont pas la même longueur")

                    dataframes.append(dataframe)
                
                except Exception as e:
                    st.error(f"Erreur dans la génération du DataFrame pour l'image {i+1}: {e}")
                    continue

                # Mettre à jour la progression des requêtes GPT-4
                gpt_progress_bar.progress((i + 1) / total_images)

            # Combiner tous les DataFrames en un seul
            if dataframes:
                data_full = pd.concat(dataframes, ignore_index=True)
                st.markdown('<h2 class="title-text">Ingrédients et Prix des Images</h2>', unsafe_allow_html=True)
                st.dataframe(data_full)
                # Sauvegarder le DataFrame combiné pour l'étape suivante
                data_full.to_csv('data_full.csv', index=False)
                st.session_state.data_full_generated = True
            else:
                st.error("Aucun DataFrame n'a été généré avec succès.")

    # Étape suivante pour utiliser data_full et recettes_igia.xlsx
    if st.session_state.get('data_full_generated'):
        if st.button("Find Recipes"):
            try:
                # Charger le fichier Excel pour les recettes
                recettes_path = 'assets/recettes-igia.xlsx'  # Assurez-vous que le fichier existe dans le répertoire de travail
                recettes_df = pd.read_excel(recettes_path, sheet_name='DATA')

                # Charger le DataFrame des ingrédients disponibles
                data_full_path = 'data_full.csv'
                data_full_df = pd.read_csv(data_full_path)

                # Extraire les ingrédients disponibles
                promo_ingredients = set(data_full_df['Ingrédients'].str.lower().str.strip())

                # Convertir la colonne "Dernière semaine d'utilisation" en numérique
                recettes_df["Dernière semaine d'utilisation"] = pd.to_numeric(recettes_df["Dernière semaine d'utilisation"], errors='coerce')

                num_rows = len(recettes_df)

                # Trouver l'indice du milieu
                mid_index = num_rows // 2

                # Diviser le DataFrame en deux parties
                first_half = recettes_df.iloc[:mid_index]
                second_half = recettes_df.iloc[mid_index:]

                # Construire le prompt pour l'API GPT-4o
                prompt = f"""
                Sélectionne les recettes dans le DataFrame `first_half` qui répondent à au moins un des deux critères suivants:
                1. La colonne `Proteine` contient une protéine qui se trouve également dans la liste `promo_ingredients` ET La recette contient au moins 3 ingrédients dans la colonne `Ingrédients` qui se trouvent aussi dans `promo_ingredients`.
                2. Si la protéine n'est pas dans `promo_ingredients`, alors au moins 5 ingrédients de la colonne `Ingrédient` dans `first_half` doivent se trouver dans `promo_ingredients`.

                Voici les DataFrames en format CSV:
                `first_half`:
                {first_half.to_csv(index=False)}

                `promo_ingredients`:
                {list(promo_ingredients)}

                Ne me génère pas du code mais simplement les recettes que tu as trouvées qui répondent aux critères. Affiche à chaque fois les éléments de `promo_ingredients` qui se retrouvent dans la recette.
                """

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                }

                payload = {
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 4096
                }

                response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                response_json = response.json()

                # Afficher la réponse
                if 'choices' in response_json and len(response_json['choices']) > 0:
                    result = response_json['choices'][0]['message']['content']
                    st.markdown('<h2 class="title-text">Suggestions de recettes pour la semaine</h2>', unsafe_allow_html=True)
                    st.write(result)
                else:
                    st.error("Aucune réponse valide reçue de l'API GPT-4")

            except Exception as e:
                st.error(f"Erreur lors de la recherche des recettes : {e}")

if __name__ == "__main__":
    main()
