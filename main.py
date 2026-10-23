from kivy.config import Config
Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
import sqlite3
import hashlib
import os
import shutil
import csv
from datetime import datetime

Window.softinput_mode = 'below_target'

CHEMIN_DB = ""
DOSSIER_RECUS = ""

ROUGE = (1, 0.3, 0.3, 1)
VERT = (0, 1, 0, 1)
BLEU = (0, 0.4, 0.8, 1)
ORANGE = (1, 0.5, 0, 1)

def preparer_chemins(base):
    os.makedirs(base, exist_ok=True)
    chemin_db = os.path.join(base, "pharmacie.db")
    if not os.path.exists(chemin_db):
        source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pharmacie.db")
        if os.path.exists(source):
            shutil.copy(source, chemin_db)
    dossier_recus = os.path.join(base, "recus")
    os.makedirs(dossier_recus, exist_ok=True)
    return chemin_db, dossier_recus

def titre(texte, taille=24):
    return Label(text=texte, font_size=sp(taille), bold=True, halign="center",
                 size_hint=(1, None), height=dp(60))

def bouton(texte, couleur=None, hauteur=50, taille=16):
    b = Button(text=texte, font_size=sp(taille), size_hint=(1, None), height=dp(hauteur))
    if couleur:
        b.background_color = couleur
    return b

def champ(hint, **kw):
    return TextInput(hint_text=hint, multiline=False, font_size=sp(16),
                     size_hint=(1, None), height=dp(45), **kw)

class PharmacieApp(App):
    def build(self):
        global CHEMIN_DB, DOSSIER_RECUS
        CHEMIN_DB, DOSSIER_RECUS = preparer_chemins(self.user_data_dir)
        self.layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        self.username_courant = ""
        self.panier = []
        self.afficher_connexion()
        return self.layout

    # ====================================================
    # CONNEXION
    # ====================================================
    def afficher_connexion(self):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("CONNEXION", 28))
        self.user_input = champ("Nom d'utilisateur")
        self.layout.add_widget(self.user_input)
        self.pass_input = champ("Mot de passe", password=True)
        self.layout.add_widget(self.pass_input)
        btn_login = bouton("SE CONNECTER", (0, 0.5, 0, 1), hauteur=56)
        btn_login.bind(on_press=self.verifier_connexion)
        self.layout.add_widget(btn_login)
        self.message = Label(text="", font_size=sp(16), color=ROUGE)
        self.layout.add_widget(self.message)

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

    # ====================================================
    # MENU PRINCIPAL (Avec bouton Alertes)
    # ====================================================
    def afficher_menu(self):
        self.layout.clear_widgets()
        self.layout.add_widget(titre(f"PHARMACIE\n{self.username_courant}", 24))
        
        # Grille de 2 colonnes
        grille = GridLayout(cols=2, spacing=dp(12))

        btn_vendre = Button(text="VENDRE", font_size=sp(18), background_color=(0, 0.6, 0, 1))
        btn_vendre.bind(on_press=self.afficher_vendre)
        
        btn_stock = Button(text="STOCK", font_size=sp(18))
        btn_stock.bind(on_press=self.afficher_stock)
        
        btn_recus = Button(text="REÇUS", font_size=sp(18))
        btn_recus.bind(on_press=self.afficher_recus)
        
        btn_alertes = Button(text="ALERTES", font_size=sp(18), background_color=ORANGE) # NOUVEAU
        btn_alertes.bind(on_press=self.afficher_alertes)
        
        btn_params = Button(text="PARAMÈTRES", font_size=sp(18))
        btn_params.bind(on_press=self.afficher_parametres)

        for b in (btn_vendre, btn_stock, btn_recus, btn_alertes, btn_params):
            grille.add_widget(b)

        self.layout.add_widget(grille)
        
        btn_quitter = bouton("QUITTER", (0.8, 0, 0, 1), hauteur=56)
        btn_quitter.bind(on_press=self.deconnexion)
        self.layout.add_widget(btn_quitter)

    def deconnexion(self, instance):
        App.get_running_app().stop()

    # ====================================================
    # NOUVEL ÉCRAN : ALERTES DE STOCK
    # ====================================================
    def afficher_alertes(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("ALERTES DE STOCK", 24))

        scroll = ScrollView()
        grille_alertes = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        grille_alertes.bind(minimum_height=grille_alertes.setter('height'))

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            # On récupère les produits avec un stock <= 10
            c.execute("SELECT nom, stock FROM medicaments WHERE stock <= 10 ORDER BY stock ASC")
            produits = c.fetchall()
            conn.close()

            if not produits:
                lbl = Label(text="Tous les stocks sont bons !\nAucun produit en alerte.", 
                            font_size=sp(18), color=VERT, size_hint_y=None, height=dp(100))
                grille_alertes.add_widget(lbl)
            else:
                for p in produits:
                    # Si stock = 0, c'est une rupture (Rouge). Sinon, c'est une alerte (Orange)
                    if p['stock'] == 0:
                        couleur = ROUGE
                        statut = "RUPTURE DE STOCK"
                    else:
                        couleur = ORANGE
                        statut = f"Stock bas : {p['stock']}"
                        
                    texte = f"{p['nom']}\n{statut}"
                    lbl = Label(text=texte, font_size=sp(16), size_hint_y=None, height=dp(60),
                                halign="left", valign="middle", color=couleur, bold=True)
                    lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
                    grille_alertes.add_widget(lbl)
                    
        except Exception as e:
            grille_alertes.add_widget(Label(text=f"Erreur : {str(e)}", font_size=sp(14), color=ROUGE))

        scroll.add_widget(grille_alertes)
        self.layout.add_widget(scroll)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1), hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    # ====================================================
    # ÉCRAN VENDRE (AVEC PANIER)
    # ====================================================
    def afficher_vendre(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("VENDRE (PANIER)", 24))

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT nom, prix_vente, stock FROM medicaments ORDER BY nom")
            produits = c.fetchall()
            conn.close()
            self.liste_produits = {p["nom"]: p for p in produits}
        except Exception:
            self.liste_produits = {}

        valeurs = list(self.liste_produits.keys())
        if not valeurs:
            valeurs = ["Aucun produit"]

        self.spinner_produit = Spinner(
            text="Sélectionnez un produit", values=valeurs, font_size=sp(16),
            size_hint=(1, None), height=dp(45), background_color=(0.2, 0.2, 0.2, 1)
        )
        self.spinner_produit.bind(text=self.maj_info_produit)
        self.layout.add_widget(self.spinner_produit)

        self.info_produit = Label(text="", font_size=sp(14), color=(0.8, 0.8, 0.8, 1), size_hint=(1, None), height=dp(25))
        self.layout.add_widget(self.info_produit)

        layout_ajout = BoxLayout(size_hint=(1, None), height=dp(45), spacing=dp(10))
        self.input_qte = champ("Quantité", input_filter='int')
        layout_ajout.add_widget(self.input_qte)
        
        btn_ajouter = bouton("AJOUTER", (0.2, 0.2, 0.8, 1), hauteur=45, taille=14)
        btn_ajouter.size_hint_x = 0.4
        btn_ajouter.bind(on_press=self.ajouter_au_panier)
        layout_ajout.add_widget(btn_ajouter)
        self.layout.add_widget(layout_ajout)

        self.scroll_panier = ScrollView(size_hint=(1, 0.4))
        self.grille_panier = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        self.grille_panier.bind(minimum_height=self.grille_panier.setter('height'))
        self.scroll_panier.add_widget(self.grille_panier)
        self.layout.add_widget(self.scroll_panier)

        self.label_total = Label(text="Total : 0 FCFA", font_size=sp(18), bold=True, color=VERT, size_hint=(1, None), height=dp(30))
        self.layout.add_widget(self.label_total)

        self.msg_vendre = Label(text="", font_size=sp(14), halign="center", size_hint=(1, None), height=dp(30))
        self.layout.add_widget(self.msg_vendre)

        layout_btns = BoxLayout(size_hint=(1, None), height=dp(50), spacing=dp(10))
        btn_vider = bouton("VIDER", (0.8, 0, 0, 1), hauteur=50, taille=14)
        btn_vider.bind(on_press=self.vider_panier)
        btn_valider = bouton("VALIDER", (0, 0.5, 0, 1), hauteur=50, taille=14)
        btn_valider.bind(on_press=self.valider_panier)
        layout_btns.add_widget(btn_vider)
        layout_btns.add_widget(btn_valider)
        self.layout.add_widget(layout_btns)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1), hauteur=45)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

        self.maj_affichage_panier()

    def maj_info_produit(self, spinner, text):
        if text in self.liste_produits:
            p = self.liste_produits[text]
            self.info_produit.text = f"Prix : {p['prix_vente']} FCFA | Stock : {p['stock']}"
        else:
            self.info_produit.text = ""

    def ajouter_au_panier(self, instance):
        nom = self.spinner_produit.text
        if nom not in self.liste_produits:
            self.msg_vendre.color = ROUGE
            self.msg_vendre.text = "Sélectionnez un produit."
            return

        try:
            qte = int(self.input_qte.text.strip())
        except ValueError:
            self.msg_vendre.color = ROUGE
            self.msg_vendre.text = "Quantité invalide."
            return

        if qte <= 0:
            self.msg_vendre.color = ROUGE
            self.msg_vendre.text = "Quantité > 0."
            return

        produit = self.liste_produits[nom]
        
        qte_deja = sum(item['qte'] for item in self.panier if item['nom'] == nom)
        if produit['stock'] < (qte_deja + qte):
            self.msg_vendre.color = ROUGE
            self.msg_vendre.text = f"Stock insuffisant ({produit['stock']} dispo)."
            return

        self.panier.append({
            'nom': nom,
            'qte': qte,
            'prix': produit['prix_vente'],
            'total': qte * produit['prix_vente']
        })
        
        self.input_qte.text = ""
        self.spinner_produit.text = "Sélectionnez un produit"
        self.info_produit.text = ""
        self.msg_vendre.text = ""
        self.maj_affichage_panier()

    def maj_affichage_panier(self):
        self.grille_panier.clear_widgets()
        total_general = 0
        
        for item in self.panier:
            texte = f"{item['qte']} x {item['nom']} = {item['total']} F"
            lbl = Label(text=texte, font_size=sp(14), size_hint_y=None, height=dp(40), halign="left", color=(1,1,1,1))
            lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
            self.grille_panier.add_widget(lbl)
            total_general += item['total']

        self.label_total.text = f"Total : {total_general} FCFA"

    def vider_panier(self, instance):
        self.panier = []
        self.maj_affichage_panier()
        self.msg_vendre.text = "Panier vidé."

    def valider_panier(self, instance):
        if not self.panier:
            self.msg_vendre.color = ROUGE
            self.msg_vendre.text = "Le panier est vide."
            return

        conn = None
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            total_general = sum(item['total'] for item in self.panier)
            date_v = datetime.now().strftime("%Y-%m-%d %H:%M")
            groupe = datetime.now().strftime("V%Y%m%d_%H%M%S")

            for item in self.panier:
                nouveau_stock = self.liste_produits[item['nom']]['stock'] - item['qte']
                c.execute("UPDATE medicaments SET stock=? WHERE nom=?", (nouveau_stock, item['nom']))
                c.execute("INSERT INTO ventes(date_vente,medicament,quantite,prix_unitaire,total,groupe) VALUES(?,?,?,?,?,?)",
                          (date_v, item['nom'], item['qte'], item['prix'], item['total'], groupe))

            c.execute("SELECT cle, valeur FROM parametres")
            params = {row["cle"]: row["valeur"] for row in c.fetchall()}
            nom_pharma = params.get("nom", "PHARMACIE")
            message_recu = params.get("message", "Merci de votre visite !")
            adresse = params.get("adresse", "")
            telephone = params.get("telephone", "")

            conn.commit()

            os.makedirs(DOSSIER_RECUS, exist_ok=True)
            nom_fichier = os.path.join(DOSSIER_RECUS, f"recu_{groupe}.txt")
            with open(nom_fichier, "w", encoding="utf-8") as f:
                f.write("========================================\n")
                f.write(f"           {nom_pharma.upper()}\n")
                if adresse: f.write(f"           {adresse}\n")
                if telephone: f.write(f"           Tel : {telephone}\n")
                f.write("========================================\n")
                f.write(f"N° : {groupe}\n")
                f.write(f"Date : {date_v}\n")
                f.write("----------------------------------------\n")
                for item in self.panier:
                    f.write(f"{item['qte']} x {item['nom']}\n")
                    f.write(f"    P.U: {item['prix']} F | Total: {item['total']} F\n")
                f.write("----------------------------------------\n")
                f.write(f"TOTAL A PAYER : {total_general} FCFA\n")
                f.write("========================================\n")
                f.write(f"{message_recu}\n")

            self.msg_vendre.color = VERT
            self.msg_vendre.text = f"Vente validée !\nTotal : {total_general} FCFA"
            self.panier = []
            self.maj_affichage_panier()
            
            c.execute("SELECT nom, prix_vente, stock FROM medicaments ORDER BY nom")
            self.liste_produits = {p["nom"]: p for p in c.fetchall()}

        except Exception as e:
            self.msg_vendre.color = ROUGE
            self.msg_vendre.text = f"Erreur : {str(e)}"
        finally:
            if conn: conn.close()

    # ====================================================
    # ÉCRAN STOCK
    # ====================================================
    def afficher_stock(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("ETAT DU STOCK", 24))

        scroll = ScrollView()
        grille_stock = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        grille_stock.bind(minimum_height=grille_stock.setter('height'))

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT nom, stock, prix_vente FROM medicaments ORDER BY nom")
            produits = c.fetchall()
            conn.close()

            for p in produits:
                texte = f"{p['nom']}\nStock : {p['stock']}   |   {p['prix_vente']} F"
                lbl = Label(text=texte, font_size=sp(14), size_hint_y=None, height=dp(56),
                            halign="left", valign="middle", color=(1, 1, 1, 1))
                lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
                grille_stock.add_widget(lbl)
        except Exception as e:
            grille_stock.add_widget(Label(text=f"Erreur : {str(e)}", font_size=sp(14), size_hint_y=None, height=dp(56)))

        scroll.add_widget(grille_stock)
        self.layout.add_widget(scroll)

        grille_btns = GridLayout(cols=2, spacing=dp(10), size_hint=(1, None), height=dp(110))
        
        btn_ajouter = bouton("AJOUTER", (0, 0.6, 0, 1), hauteur=48)
        btn_ajouter.bind(on_press=self.afficher_ajout_produit)
        grille_btns.add_widget(btn_ajouter)

        btn_modifier = bouton("MODIFIER / SUPPR.", (0.8, 0.4, 0, 1), hauteur=48)
        btn_modifier.bind(on_press=self.afficher_modifier_produit)
        grille_btns.add_widget(btn_modifier)

        btn_export = bouton("EXPORTER CSV", BLEU, hauteur=48)
        btn_export.bind(on_press=self.exporter_csv)
        grille_btns.add_widget(btn_export)

        btn_import = bouton("IMPORTER CSV", (0.6, 0, 0.6, 1), hauteur=48)
        btn_import.bind(on_press=self.afficher_import_csv)
        grille_btns.add_widget(btn_import)

        self.layout.add_widget(grille_btns)

        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1), hauteur=48)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    # ====================================================
    # AJOUTER UN PRODUIT
    # ====================================================
    def afficher_ajout_produit(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("NOUVEAU PRODUIT", 24))
        self.nouveau_nom = champ("Nom du produit")
        self.layout.add_widget(self.nouveau_nom)
        self.nouveau_prix = champ("Prix de vente (FCFA)", input_filter='float')
        self.layout.add_widget(self.nouveau_prix)
        self.nouveau_stock = champ("Quantité initiale en stock", input_filter='int')
        self.layout.add_widget(self.nouveau_stock)
        self.msg_ajout = Label(text="", font_size=sp(16), halign="center")
        self.layout.add_widget(self.msg_ajout)
        btn_sauver = bouton("ENREGISTRER LE PRODUIT", (0, 0.6, 0, 1), hauteur=56)
        btn_sauver.bind(on_press=self.sauvegarder_nouveau_produit)
        self.layout.add_widget(btn_sauver)
        btn_retour = bouton("RETOUR", (0.5, 0.5, 0.5, 1), hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_stock(None))
        self.layout.add_widget(btn_retour)

    def sauvegarder_nouveau_produit(self, instance):
        nom = self.nouveau_nom.text.strip()
        pr
