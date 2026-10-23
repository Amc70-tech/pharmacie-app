from kivy.config import Config
Config.set('graphics', 'orientation', 'portrait')
Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp, sp
import sqlite3
import hashlib
import os
from datetime import datetime
import shutil

CHEMIN_DB = ""
DOSSIER_RECUS = ""

def preparer_chemins():
    try:
        base = App.get_running_app().user_data_dir
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base, exist_ok=True)
    chemin_db = os.path.join(base, "pharmacie.db")
    if not os.path.exists(chemin_db):
        source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pharmacie.db")
        if os.path.exists(source):
            shutil.copy(source, chemin_db)
    dossier_recus = os.path.join(base, "recus")
    os.makedirs(dossier_recus, exist_ok=True)
    return chemin_db, dossier_recus

class PharmacieApp(App):
    def build(self):
        global CHEMIN_DB, DOSSIER_RECUS
        CHEMIN_DB, DOSSIER_RECUS = preparer_chemins()
        self.layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
        self.username_courant = ""
        self.afficher_connexion()
        return self.layout

    def afficher_connexion(self):
        self.layout.clear_widgets()
        
        self.layout.add_widget(Label(text="", size_hint=(1, 0.1)))
        titre = Label(text="CONNEXION", font_size=sp(30), size_hint=(1, None), height=dp(50), color=(1,1,1,1))
        self.layout.add_widget(titre)
        self.layout.add_widget(Label(text="", size_hint=(1, 0.1)))
        
        self.user_input = TextInput(hint_text="Nom d'utilisateur", multiline=False, font_size=sp(18), size_hint=(1, None), height=dp(50), padding_y=(dp(10), dp(10)))
        self.layout.add_widget(self.user_input)
        
        self.pass_input = TextInput(hint_text="Mot de passe", password=True, multiline=False, font_size=sp(18), size_hint=(1, None), height=dp(50), padding_y=(dp(10), dp(10)))
        self.layout.add_widget(self.pass_input)
        
        self.layout.add_widget(Label(text="", size_hint=(1, 0.1)))
        
        btn_login = Button(text="SE CONNECTER", font_size=sp(20), size_hint=(1, None), height=dp(60), background_color=(0, 0.5, 0, 1), bold=True)
        btn_login.bind(on_press=self.verifier_connexion)
        self.layout.add_widget(btn_login)
        
        self.message = Label(text="", font_size=sp(16), color=(1, 0, 0, 1), size_hint=(1, None), height=dp(40))
        self.layout.add_widget(self.message)
        self.layout.add_widget(Label(text="", size_hint=(1, 0.2)))

    def verifier_connexion(self, instance):
        username = self.user_input.text.strip()
        password = self.pass_input.text.strip()
        
        if not username or not password:
            self.message.text = "Veuillez remplir tous les champs."
            return
            
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM utilisateurs WHERE username=?", (username,))
            user = c.fetchone()
            conn.close()
            
            if user:
                sel = user["sel"]
                h = hashlib.sha256((sel + password).encode()).hexdigest()
                if h == user["password_hash"]:
                    self.username_courant = username
                    self.afficher_menu()
                else:
                    self.message.text = "Mot de passe incorrect."
            else:
                self.message.text = "Utilisateur introuvable."
                
        except Exception as e:
            self.message.text = f"Erreur : {str(e)}"

    def afficher_menu(self):
        self.layout.clear_widgets()
        
        titre = Label(text=f"PHARMACIE\n{self.username_courant}", font_size=sp(26), size_hint=(1, 0.2), color=(1,1,1,1))
        self.layout.add_widget(titre)
        
        grille = GridLayout(cols=2, spacing=dp(15), size_hint=(1, 0.6))
        
        btn_vendre = Button(text="VENDRE", font_size=sp(20), background_color=(0, 0.6, 0, 1), bold=True)
        btn_vendre.bind(on_press=self.afficher_vendre)
        
        btn_stock = Button(text="STOCK", font_size=sp(20), background_color=(0.2, 0.2, 0.2, 1))
        btn_stock.bind(on_press=self.afficher_stock)
        
        btn_recus = Button(text="REÇUS", font_size=sp(20), background_color=(0.2, 0.2, 0.2, 1))
        btn_recus.bind(on_press=self.afficher_recus)
        
        btn_params = Button(text="PARAMÈTRES", font_size=sp(20), background_color=(0.2, 0.2, 0.2, 1))
        btn_params.bind(on_press=self.afficher_parametres)
        
        grille.add_widget(btn_vendre)
        grille.add_widget(btn_stock)
        grille.add_widget(btn_recus)
        grille.add_widget(btn_params)
        
        self.layout.add_widget(grille)
        
        btn_quitter = Button(text="DÉCONNEXION", font_size=sp(18), size_hint=(1, None), height=dp(50), background_color=(0.8, 0, 0, 1))
        btn_quitter.bind(on_press=self.deconnexion)
        self.layout.add_widget(btn_quitter)
        
    def deconnexion(self, instance):
        App.get_running_app().stop()

    def afficher_vendre(self, instance):
        self.layout.clear_widgets()
        
        titre = Label(text="VENDRE", font_size=sp(28), size_hint=(1, None), height=dp(60), color=(1,1,1,1))
        self.layout.add_widget(titre)
        
        self.input_nom = TextInput(hint_text="Nom du produit", multiline=False, font_size=sp(18), size_hint=(1, None), height=dp(50), padding_y=(dp(10), dp(10)))
        self.layout.add_widget(self.input_nom)
        
        self.input_qte = TextInput(hint_text="Quantité", multiline=False, font_size=sp(18), size_hint=(1, None), height=dp(50), input_filter='int', padding_y=(dp(10), dp(10)))
        self.layout.add_widget(self.input_qte)
        
        self.msg_vendre = Label(text="", font_size=sp(16), size_hint=(1, 0.3), color=(1,1,1,1))
        self.layout.add_widget(self.msg_vendre)
        
        btn_valider = Button(text="VALIDER LA VENTE", font_size=sp(20), size_hint=(1, None), height=dp(60), background_color=(0, 0.5, 0, 1), bold=True)
        btn_valider.bind(on_press=self.valider_vente)
        self.layout.add_widget(btn_valider)
        
        self.layout.add_widget(Label(text="", size_hint=(1, 0.05)))
        
        btn_retour = Button(text="RETOUR", font_size=sp(18), size_hint=(1, None), height=dp(50), background_color=(0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    def valider_vente(self, instance):
        nom = self.input_nom.text.strip()
        try:
            qte = int(self.input_qte.text.strip())
        except:
            self.msg_vendre.text = "Erreur : Quantité invalide."
            return
            
        if not nom or qte <= 0:
            self.msg_vendre.text = "Erreur : Remplissez les champs."
            return
            
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute("SELECT * FROM medicaments WHERE LOWER(nom) LIKE ?", (f"%{nom.lower()}%",))
            produit = c.fetchone()
            
            if not produit:
                self.msg_vendre.text = "Produit introuvable."
                conn.close()
                return
                
            if produit["stock"] < qte:
                self.msg_vendre.text = f"Stock insuffisant ({produit['stock']} dispo)."
                conn.close()
                return
                
            nouveau_stock = produit["stock"] - qte
            c.execute("UPDATE medicaments SET stock=? WHERE id=?", (nouveau_stock, produit["id"]))
            
            total = qte * produit["prix_vente"]
            date_v = datetime.now().strftime("%Y-%m-%d %H:%M")
            groupe = datetime.now().strftime("V%Y%m%d_%H%M%S")
            
            c.execute("INSERT INTO ventes(date_vente,medicament,quantite,prix_unitaire,total,groupe) VALUES(?,?,?,?,?,?)",
                      (date_v, produit["nom"], qte, produit["prix_vente"], total, groupe))
            
            c.execute("SELECT cle, valeur FROM parametres")
            params = {row["cle"]: row["valeur"] for row in c.fetchall()}
            nom_pharma = params.get("nom", "PHARMACIE")
            message_recu = params.get("message", "Merci de votre visite !")
            adresse = params.get("adresse", "")
            telephone = params.get("telephone", "")
            
            conn.commit()
            conn.close()
            
            if not os.path.exists(DOSSIER_RECUS):
                os.makedirs(DOSSIER_RECUS)
            
            nom_fichier = f"{DOSSIER_RECUS}/recu_{groupe}.txt"
            with open(nom_fichier, "w", encoding="utf-8") as f:
                f.write("========================================\n")
                f.write(f"           {nom_pharma.upper()}\n")
                if adresse: f.write(f"           {adresse}\n")
                if telephone: f.write(f"           Tel : {telephone}\n")
                f.write("========================================\n")
                f.write(f"N° : {groupe}\n")
                f.write(f"Date : {date_v}\n")
                f.write("----------------------------------------\n")
                f.write(f"Produit : {produit['nom']}\n")
                f.write(f"Quantite : {qte}\n")
                f.write(f"Prix U : {produit['prix_vente']} FCFA\n")
                f.write("----------------------------------------\n")
                f.write(f"TOTAL : {total} FCFA\n")
                f.write("========================================\n")
                f.write(f"{message_recu}\n")
            
            self.msg_vendre.color = (0, 1, 0, 1)
            self.msg_vendre.text = f"Vendu : {qte} x {produit['nom']}\nTotal : {total} FCFA\nReçu généré !"
            self.input_nom.text = ""
            self.input_qte.text = ""
            
        except Exception as e:
            self.msg_vendre.text = f"Erreur : {str(e)}"

    def afficher_stock(self, instance):
        self.layout.clear_widgets()
        
        titre = Label(text="ETAT DU STOCK", font_size=sp(28), size_hint=(1, None), height=dp(60), color=(1,1,1,1))
        self.layout.add_widget(titre)
        
        scroll = ScrollView(size_hint=(1, 0.8))
        grille_stock = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        grille_stock.bind(minimum_height=grille_stock.setter('height'))
        
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT nom, stock, prix_vente FROM medicaments ORDER BY nom")
            produits = c.fetchall()
            conn.close()
            
            for p in produits:
                texte = f"{p['nom'][:25]} | Stock: {p['stock']} | {p['prix_vente']} F"
                lbl = Label(text=texte, font_size=sp(16), size_hint_y=None, height=dp(40), color=(1,1,1,1))
                grille_stock.add_widget(lbl)
                
        except Exception as e:
            lbl = Label(text=f"Erreur : {str(e)}", font_size=sp(16), color=(1,0,0,1))
            grille_stock.add_widget(lbl)
            
        scroll.add_widget(grille_stock)
        self.layout.add_widget(scroll)
        
        btn_retour = Button(text="RETOUR", font_size=sp(18), size_hint=(1, None), height=dp(50), background_color=(0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    def afficher_recus(self, instance):
        self.layout.clear_widgets()
        
        titre = Label(text="DERNIERS REÇUS", font_size=sp(28), size_hint=(1, None), height=dp(60), color=(1,1,1,1))
        self.layout.add_widget(titre)
        
        scroll = ScrollView(size_hint=(1, 0.8))
        grille_recus = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        grille_recus.bind(minimum_height=grille_recus.setter('height'))
        
        try:
            if os.path.exists(DOSSIER_RECUS):
                fichiers = sorted([f for f in os.listdir(DOSSIER_RECUS) if f.endswith(".txt")], reverse=True)
                if not fichiers:
                    lbl = Label(text="Aucun reçu pour le moment.", font_size=sp(18), color=(1,1,1,1))
                    grille_recus.add_widget(lbl)
                else:
                    for f in fichiers[:20]:
                        btn = Button(text=f, size_hint_y=None, height=dp(50), font_size=sp(14))
                        btn.bind(on_press=lambda x, nom_fichier=f: self.ouvrir_recu(nom_fichier))
                        grille_recus.add_widget(btn)
            else:
                lbl = Label(text="Aucun reçu. Faites une vente !", font_size=sp(18), color=(1,1,1,1))
                grille_recus.add_widget(lbl)
                
        except Exception as e:
            lbl = Label(text=f"Erreur : {str(e)}", font_size=sp(16), color=(1,0,0,1))
            grille_recus.add_widget(lbl)
            
        scroll.add_widget(grille_recus)
        self.layout.add_widget(scroll)
        
        btn_retour = Button(text="RETOUR", font_size=sp(18), size_hint=(1, None), height=dp(50), background_color=(0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    def ouvrir_recu(self, nom_fichier):
        self.layout.clear_widgets()
        
        titre = Label(text="DÉTAIL DU REÇU", font_size=sp(24), size_hint=(1, None), height=dp(60), color=(1,1,1,1))
        self.layout.add_widget(titre)
        
        scroll = ScrollView(size_hint=(1, 0.8))
        
        chemin = os.path.join(DOSSIER_RECUS, nom_fichier)
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                contenu = f.read()
        except Exception as e:
            contenu = f"Erreur de lecture : {e}"
            
        lbl_texte = Label(
            text=contenu, 
            font_size=sp(15), 
            size_hint_y=None, 
            text_size=(self.layout.width - dp(40), None),
            halign="left", 
            valign="top",
            color=(1, 1, 1, 1)
        )
        
        lbl_texte.bind(
            width=lambda *x: setattr(lbl_texte, 'text_size', (lbl_texte.width, None)),
            texture_size=lambda *x: setattr(lbl_texte, 'height', lbl_texte.texture_size[1])
        )
        
        scroll.add_widget(lbl_texte)
        self.layout.add_widget(scroll)
        
        btn_retour = Button(text="RETOUR", font_size=sp(18), size_hint=(1, None), height=dp(50), background_color=(0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_recus(None))
        self.layout.add_widget(btn_retour)

    def afficher_parametres(self, instance):
        self.layout.clear_widgets()
        
        titre = Label(text="PARAMÈTRES", font_size=sp(28), size_hint=(1, None), height=dp(60), color=(1,1,1,1))
        self.layout.add_widget(titre)
        
        scroll = ScrollView(size_hint=(1, 0.75))
        grille = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        grille.bind(minimum_height=grille.setter('height'))
        
        params = {}
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT cle, valeur FROM parametres")
            for row in c.fetchall():
                params[row["cle"]] = row["valeur"]
            conn.close()
        except:
            pass
            
        self.param_inputs = {}
        champs = [
            ("nom", "Nom de la pharmacie"),
            ("adresse", "Adresse"),
            ("telephone", "Téléphone"),
            ("email", "Email"),
            ("nif", "NIF"),
            ("message", "Message du reçu")
        ]
        
        for cle, label_txt in champs:
            lbl = Label(text=label_txt, size_hint_y=None, height=dp(30), font_size=sp(14), color=(0.8, 0.8, 0.8, 1))
            inp = TextInput(text=params.get(cle, ""), multiline=False, size_hint_y=None, height=dp(45), font_size=sp(16), padding_y=(dp(10), dp(10)))
            self.param_inputs[cle] = inp
            grille.add_widget(lbl)
            grille.add_widget(inp)
            grille.add_widget(Label(text="", size_hint_y=None, height=dp(10)))
            
        scroll.add_widget(grille)
        self.layout.add_widget(scroll)
        
        self.msg_params = Label(text="", font_size=sp(16), size_hint=(1, None), height=dp(30))
        self.layout.add_widget(self.msg_params)
        
        btn_sauver = Button(text="ENREGISTRER", font_size=sp(18), size_hint=(1, None), height=dp(50), background_color=(0, 0.6, 0, 1), bold=True)
        btn_sauver.bind(on_press=self.sauvegarder_parametres)
        self.layout.add_widget(btn_sauver)
        
        self.layout.add_widget(Label(text="", size_hint=(1, None), height=dp(10)))
        
        btn_retour = Button(text="RETOUR", font_size=sp(18), size_hint=(1, None), height=dp(50), background_color=(0.5, 0.5, 0.5, 1))
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    def sauvegarder_parametres(self, instance):
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            for cle, inp in self.param_inputs.items():
                valeur = inp.text.strip()
                if valeur:
                    c.execute("INSERT OR REPLACE INTO parametres (cle, valeur) VALUES (?, ?)", (cle, valeur))
            conn.commit()
            conn.close()
            self.msg_params.color = (0, 1, 0, 1)
            self.msg_params.text = "Paramètres sauvegardés !"
        except Exception as e:
            self.msg_params.color = (1, 0, 0, 1)
            self.msg_params.text = f"Erreur : {str(e)}"

if __name__ == '__main__':
    PharmacieApp().run()
