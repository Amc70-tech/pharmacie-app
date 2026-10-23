# -*- coding: utf-8 -*-
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
import sqlite3
import hashlib
import os
import shutil
import csv
import traceback
from datetime import datetime

Window.softinput_mode = 'below_target'

CHEMIN_DB = ""
DOSSIER_RECUS = ""

ROUGE = (1, 0.3, 0.3, 1)
VERT = (0, 1, 0, 1)
BLEU = (0, 0.4, 0.8, 1)
ORANGE = (1, 0.5, 0, 1)
VIOLET = (0.6, 0.2, 0.8, 1)
GRIS = (0.5, 0.5, 0.5, 1)

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

def migrer_base_de_donnees():
    """Met à jour la base de données pour ajouter les rôles et le suivi des vendeurs."""
    try:
        conn = sqlite3.connect(CHEMIN_DB)
        c = conn.cursor()
        
        # 1. Vérifier la colonne 'role' dans utilisateurs
        c.execute("PRAGMA table_info(utilisateurs)")
        colonnes_users = [info[1] for info in c.fetchall()]
        if "role" not in colonnes_users:
            c.execute("ALTER TABLE utilisateurs ADD COLUMN role TEXT DEFAULT 'caissier'")
            c.execute("UPDATE utilisateurs SET role='admin' WHERE username='admin'")

        # 2. Vérifier la colonne 'vendeur' dans ventes
        c.execute("PRAGMA table_info(ventes)")
        colonnes_ventes = [info[1] for info in c.fetchall()]
        if "vendeur" not in colonnes_ventes:
            c.execute("ALTER TABLE ventes ADD COLUMN vendeur TEXT DEFAULT 'Inconnu'")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur migration : {e}")

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
        try:
            global CHEMIN_DB, DOSSIER_RECUS
            CHEMIN_DB, DOSSIER_RECUS = preparer_chemins(self.user_data_dir)
            migrer_base_de_donnees()
            self.layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
            self.username_courant = ""
            self.role_courant = ""
            self.panier = []
            self.afficher_connexion()
        except Exception as e:
            err = traceback.format_exc()
            self.layout = BoxLayout(orientation='vertical', padding=dp(15))
            self.layout.add_widget(Label(text=f"Erreur au démarrage :\n{str(e)}\n\n{err}", color=ROUGE, font_size=sp(12)))
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
                    self.role_courant = user["role"]
                    self.user_input.text = ""
                    self.pass_input.text = ""
                    self.message.text = ""
                    self.afficher_menu()
                else:
                    self.message.text = "Mot de passe incorrect."
            else:
                self.message.text = "Utilisateur introuvable."
        except Exception as e:
            self.message.text = f"Erreur : {str(e)}"

    # ====================================================
    # MENU PRINCIPAL
    # ====================================================
    def afficher_menu(self):
        self.layout.clear_widgets()
        self.layout.add_widget(titre(f"PHARMACIE\n{self.username_courant}", 24))
        
        grille = GridLayout(cols=2, spacing=dp(10))

        btn_vendre = Button(text="VENDRE", font_size=sp(18), background_color=(0, 0.6, 0, 1))
        btn_vendre.bind(on_press=self.afficher_vendre)
        grille.add_widget(btn_vendre)

        btn_recus = Button(text="REÇUS", font_size=sp(18))
        btn_recus.bind(on_press=self.afficher_recus)
        grille.add_widget(btn_recus)

        if self.role_courant == 'admin':
            btn_stock = Button(text="STOCK", font_size=sp(18))
            btn_stock.bind(on_press=self.afficher_stock)
            grille.add_widget(btn_stock)
            
            btn_alertes = Button(text="ALERTES", font_size=sp(18), background_color=ORANGE)
            btn_alertes.bind(on_press=self.afficher_alertes)
            grille.add_widget(btn_alertes)
            
            btn_bilan = Button(text="BILAN DU JOUR", font_size=sp(16), background_color=VIOLET)
            btn_bilan.bind(on_press=self.afficher_bilan)
            grille.add_widget(btn_bilan)

            # NOUVEAU BOUTON : Suivi des caissiers
            btn_suivi = Button(text="SUIVI CAISSIERS", font_size=sp(16), background_color=(0.8, 0.2, 0.2, 1))
            btn_suivi.bind(on_press=self.afficher_suivi_caissiers)
            grille.add_widget(btn_suivi)
            
            btn_params = Button(text="PARAMÈTRES", font_size=sp(18))
            btn_params.bind(on_press=self.afficher_parametres)
            grille.add_widget(btn_params)

        self.layout.add_widget(grille)
        
        btn_quitter = bouton("DÉCONNEXION", (0.8, 0, 0, 1), hauteur=56)
        btn_quitter.bind(on_press=self.deconnexion)
        self.layout.add_widget(btn_quitter)

    def deconnexion(self, instance):
        self.username_courant = ""
        self.role_courant = ""
        self.panier = []
        self.afficher_connexion()

    # ====================================================
    # SUIVI DES CAISSIERS (Nouveau)
    # ====================================================
    def afficher_suivi_caissiers(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("SUIVI DES CAISSIERS\n(Aujourd'hui)", 20))

        scroll = ScrollView(size_hint=(1, 0.8))
        grille_suivi = GridLayout(cols=1, spacing=dp(10), size_hint_y=None)
        grille_suivi.bind(minimum_height=grille_suivi.setter('height'))

        date_auj = datetime.now().strftime("%Y-%m-%d")

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # On regroupe les ventes par vendeur pour aujourd'hui
            c.execute("""
                SELECT vendeur, SUM(total) as ca, COUNT(DISTINCT groupe) as tickets 
                FROM ventes 
                WHERE date_vente LIKE ? 
                GROUP BY vendeur
            """, (f"{date_auj}%",))
            resultats = c.fetchall()
            conn.close()

            if not resultats:
                grille_suivi.add_widget(Label(text="Aucune vente enregistrée aujourd'hui.", 
                                              font_size=sp(16), color=GRIS, size_hint_y=None, height=dp(60)))
            else:
                for r in resultats:
                    texte = f"👤 Vendeur : {r['vendeur'].upper()}\n" \
                            f"💰 Total : {r['ca']} FCFA\n" \
                            f"🧾 Tickets : {r['tickets']}"
                    
                    lbl = Label(text=texte, font_size=sp(16), size_hint_y=None, height=dp(80),
                                halign="left", valign="middle", color=(1, 1, 1, 1))
                    lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
                    
                    # Un petit fond gris pour séparer les vendeurs
                    box = BoxLayout(size_hint_y=None, height=dp(80), padding=dp(10))
                    box.canvas.before.clear()
                    with box.canvas.before:
                        from kivy.graphics import Color, Rectangle
                        Color(0.15, 0.15, 0.15, 1)
                        Rectangle(pos=box.pos, size=box.size)
                    
                    box.add_widget(lbl)
                    grille_suivi.add_widget(box)
                    
        except Exception as e:
            grille_suivi.add_widget(Label(text=f"Erreur : {str(e)}", font_size=sp(14), color=ROUGE))

        scroll.add_widget(grille_suivi)
        self.layout.add_widget(scroll)

        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    # ====================================================
    # BILAN DU JOUR
    # ====================================================
    def afficher_bilan(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("BILAN GLOBAL DU JOUR", 24))

        date_auj = datetime.now().strftime("%Y-%m-%d")
        
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT SUM(total) as ca, COUNT(DISTINCT groupe) as nb_ventes, SUM(quantite) as nb_articles FROM ventes WHERE date_vente LIKE ?", (f"{date_auj}%",))
            res = c.fetchone()
            conn.close()

            ca = res['ca'] if res['ca'] else 0
            nb_ventes = res['nb_ventes'] if res['nb_ventes'] else 0
            nb_articles = res['nb_articles'] if res['nb_articles'] else 0

            box_stats = BoxLayout(orientation='vertical', spacing=dp(20), padding=dp(20))
            
            lbl_ca = Label(text=f"Chiffre d'Affaires :\n{ca} FCFA", font_size=sp(28), bold=True, color=VERT)
            lbl_ventes = Label(text=f"Nombre de tickets :\n{nb_ventes}", font_size=sp(22), color=(1,1,1,1))
            lbl_articles = Label(text=f"Articles vendus :\n{nb_articles}", font_size=sp(22), color=(1,1,1,1))

            box_stats.add_widget(lbl_ca)
            box_stats.add_widget(lbl_ventes)
            box_stats.add_widget(lbl_articles)

            self.layout.add_widget(box_stats)

        except Exception as e:
            self.layout.add_widget(Label(text=f"Erreur : {str(e)}", font_size=sp(16), color=ROUGE))

        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    # ====================================================
    # ALERTES
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
            c.execute("SELECT nom, stock FROM medicaments WHERE stock <= 10 ORDER BY stock ASC")
            produits = c.fetchall()
            conn.close()

            if not produits:
                lbl = Label(text="Tous les stocks sont bons !\nAucun produit en alerte.", 
                            font_size=sp(18), color=VERT, size_hint_y=None, height=dp(100))
                grille_alertes.add_widget(lbl)
            else:
                for p in produits:
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

        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    # ====================================================
    # VENDRE
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

        btn_retour = bouton("RETOUR", GRIS, hauteur=45)
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
                # MODIFICATION ICI : On enregistre le vendeur
                c.execute("INSERT INTO ventes(date_vente,medicament,quantite,prix_unitaire,total,groupe,vendeur) VALUES(?,?,?,?,?,?,?)",
                          (date_v, item['nom'], item['qte'], item['prix'], item['total'], groupe, self.username_courant))

            c.execute("SELECT cle, valeur FROM parametres")
            params = {row["cle"]: row["valeur"] for row in c.fetchall()}
            nom_pharma = params.get("nom", "DILEROM")
            message_recu = params.get("message", "Merci de votre visite !")
            adresse = params.get("adresse", "")
            telephone = params.get("telephone", "")

            conn.commit()

            os.makedirs(DOSSIER_RECUS, exist_ok=True)
            nom_fichier = os.path.join(DOSSIER_RECUS, f"recu_{groupe}.txt")
            with open(nom_fichier, "w", encoding="utf-8") as f:
                f.write("========================================\n")
                f.write(f"           PHARMACIE {nom_pharma.upper()}\n")
                if adresse: f.write(f"           {adresse}\n")
                if telephone: f.write(f"           Tel : {telephone}\n")
                f.write("========================================\n")
                f.write(f"N° : {groupe}\n")
                f.write(f"Date : {date_v}\n")
                f.write(f"Vendeur : {self.username_courant.upper()}\n") # MODIFICATION ICI : Affiché sur le reçu
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
    # STOCK
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

        btn_retour = bouton("RETOUR", GRIS, hauteur=48)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

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
        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_stock(None))
        self.layout.add_widget(btn_retour)

    def sauvegarder_nouveau_produit(self, instance):
        nom = self.nouveau_nom.text.strip()
        prix_str = self.nouveau_prix.text.strip()
        stock_str = self.nouveau_stock.text.strip()
        if not nom or not prix_str or not stock_str:
            self.msg_ajout.color = ROUGE
            self.msg_ajout.text = "Veuillez remplir tous les champs."
            return
        try:
            prix = float(prix_str)
            stock = int(stock_str)
        except ValueError:
            self.msg_ajout.color = ROUGE
            self.msg_ajout.text = "Prix ou stock invalide."
            return
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            c.execute("SELECT id FROM medicaments WHERE LOWER(nom) = ?", (nom.lower(),))
            if c.fetchone():
                self.msg_ajout.color = ROUGE
                self.msg_ajout.text = "Ce produit existe déjà."
                conn.close()
                return
            c.execute("INSERT INTO medicaments (nom, prix_vente, stock) VALUES (?, ?, ?)", (nom, prix, stock))
            conn.commit()
            conn.close()
            self.msg_ajout.color = VERT
            self.msg_ajout.text = "Produit ajouté avec succès !"
            self.nouveau_nom.text = ""
            self.nouveau_prix.text = ""
            self.nouveau_stock.text = ""
        except Exception as e:
            self.msg_ajout.color = ROUGE
            self.msg_ajout.text = f"Erreur : {str(e)}"

    def afficher_modifier_produit(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("MODIFIER / SUPPRIMER", 24))
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT nom, prix_vente, stock FROM medicaments ORDER BY nom")
            produits = c.fetchall()
            conn.close()
            self.liste_produits_mod = {p["nom"]: p for p in produits}
        except Exception:
            self.liste_produits_mod = {}
        valeurs = list(self.liste_produits_mod.keys())
        if not valeurs:
            valeurs = ["Aucun produit"]
        self.spinner_mod = Spinner(text="Sélectionnez un produit", values=valeurs, font_size=sp(16), size_hint=(1, None), height=dp(50), background_color=(0.2, 0.2, 0.2, 1))
        self.spinner_mod.bind(text=self.remplir_champs_mod)
        self.layout.add_widget(self.spinner_mod)
        self.mod_prix = champ("Nouveau prix (FCFA)", input_filter='float')
        self.layout.add_widget(self.mod_prix)
        self.mod_stock = champ("Nouveau stock", input_filter='int')
        self.layout.add_widget(self.mod_stock)
        self.msg_mod = Label(text="", font_size=sp(16), halign="center")
        self.layout.add_widget(self.msg_mod)
        btn_maj = bouton("METTRE À JOUR", (0, 0.6, 0, 1), hauteur=56)
        btn_maj.bind(on_press=self.mettre_a_jour_produit)
        self.layout.add_widget(btn_maj)
        btn_suppr = bouton("SUPPRIMER DÉFINITIVEMENT", (0.8, 0, 0, 1), hauteur=56)
        btn_suppr.bind(on_press=self.supprimer_produit)
        self.layout.add_widget(btn_suppr)
        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_stock(None))
        self.layout.add_widget(btn_retour)

    def remplir_champs_mod(self, spinner, text):
        if text in self.liste_produits_mod:
            p = self.liste_produits_mod[text]
            self.mod_prix.text = str(p['prix_vente'])
            self.mod_stock.text = str(p['stock'])
            self.msg_mod.text = ""

    def mettre_a_jour_produit(self, instance):
        nom = self.spinner_mod.text
        if nom not in self.liste_produits_mod:
            self.msg_mod.color = ROUGE
            self.msg_mod.text = "Sélectionnez un produit valide."
            return
        try:
            prix = float(self.mod_prix.text.strip())
            stock = int(self.mod_stock.text.strip())
        except ValueError:
            self.msg_mod.color = ROUGE
            self.msg_mod.text = "Valeurs invalides."
            return
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            c.execute("UPDATE medicaments SET prix_vente=?, stock=? WHERE nom=?", (prix, stock, nom))
            conn.commit()
            conn.close()
            self.msg_mod.color = VERT
            self.msg_mod.text = "Produit mis à jour !"
        except Exception as e:
            self.msg_mod.color = ROUGE
            self.msg_mod.text = f"Erreur : {str(e)}"

    def supprimer_produit(self, instance):
        nom = self.spinner_mod.text
        if nom not in self.liste_produits_mod:
            self.msg_mod.color = ROUGE
            self.msg_mod.text = "Sélectionnez un produit valide."
            return
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            c.execute("DELETE FROM medicaments WHERE nom=?", (nom,))
            conn.commit()
            conn.close()
            self.msg_mod.color = VERT
            self.msg_mod.text = "Produit supprimé !"
            self.spinner_mod.text = "Sélectionnez un produit"
            self.mod_prix.text = ""
            self.mod_stock.text = ""
            del self.liste_produits_mod[nom]
            self.spinner_mod.values = list(self.liste_produits_mod.keys())
        except Exception as e:
            self.msg_mod.color = ROUGE
            self.msg_mod.text = f"Erreur : {str(e)}"

    def exporter_csv(self, instance):
        try:
            chemin_csv = os.path.join(App.get_running_app().user_data_dir, "export_stock.csv")
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            c.execute("SELECT nom, prix_vente, stock FROM medicaments")
            produits = c.fetchall()
            conn.close()
            with open(chemin_csv, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['Nom', 'Prix', 'Stock'])
                for p in produits:
                    writer.writerow([p[0], p[1], p[2]])
            self._show_popup("Exportation réussie", f"Fichier sauvegardé ici :\n{chemin_csv}")
        except Exception as e:
            self._show_popup("Erreur d'exportation", str(e))

    def afficher_import_csv(self, instance):
        try:
            from kivy.uix.filechooser import FileChooserListView
            content = BoxLayout(orientation='vertical', spacing=dp(10))
            filechooser = FileChooserListView(path=App.get_running_app().user_data_dir, filters=['*.csv'])
            content.add_widget(filechooser)
            layout_btns = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(10))
            btn_annuler = Button(text="Annuler")
            btn_importer = Button(text="Importer")
            layout_btns.add_widget(btn_annuler)
            layout_btns.add_widget(btn_importer)
            content.add_widget(layout_btns)
            popup = Popup(title="Sélectionner un fichier CSV", content=content, size_hint=(0.9, 0.9))
            btn_annuler.bind(on_press=popup.dismiss)
            btn_importer.bind(on_press=lambda x: self.importer_csv(filechooser.selection, popup))
            popup.open()
        except Exception as e:
            self._show_popup("Erreur", f"Impossible d'ouvrir l'explorateur de fichiers :\n{str(e)}")

    def importer_csv(self, selection, popup):
        if not selection:
            return
        chemin = selection[0]
        popup.dismiss()
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            count = 0
            with open(chemin, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                next(reader, None)
                for row in reader:
                    if len(row) >= 3:
                        nom = row[0].strip()
                        try:
                            prix = float(row[1])
                            stock = int(row[2])
                            c.execute("INSERT OR REPLACE INTO medicaments (nom, prix_vente, stock) VALUES (?, ?, ?)", (nom, prix, stock))
                            count += 1
                        except ValueError:
                            continue
            conn.commit()
            conn.close()
            self._show_popup("Importation réussie", f"{count} produits importés/mis à jour.")
        except Exception as e:
            self._show_popup("Erreur d'importation", str(e))

    def _show_popup(self, titre, message):
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(Label(text=message, halign='center'))
        btn = Button(text="OK", size_hint=(1, None), height=dp(50))
        content.add_widget(btn)
        popup = Popup(title=titre, content=content, size_hint=(0.8, 0.4))
        btn.bind(on_press=popup.dismiss)
        popup.open()

    # ====================================================
    # REÇUS
    # ====================================================
    def afficher_recus(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("DERNIERS REÇUS", 24))
        scroll = ScrollView()
        grille_recus = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        grille_recus.bind(minimum_height=grille_recus.setter('height'))
        try:
            fichiers = []
            if os.path.exists(DOSSIER_RECUS):
                fichiers = sorted([f for f in os.listdir(DOSSIER_RECUS) if f.endswith(".txt")], reverse=True)
            if not fichiers:
                grille_recus.add_widget(Label(text="Aucun reçu pour le moment.\nFaites une vente !", font_size=sp(16), size_hint_y=None, height=dp(80)))
            else:
                for f in fichiers[:20]:
                    btn = Button(text=f, size_hint_y=None, height=dp(48), font_size=sp(14))
                    btn.bind(on_press=lambda x, nom_fichier=f: self.ouvrir_recu(nom_fichier))
                    grille_recus.add_widget(btn)
        except Exception as e:
            grille_recus.add_widget(Label(text=f"Erreur : {str(e)}", font_size=sp(14), size_hint_y=None, height=dp(56)))
        scroll.add_widget(grille_recus)
        self.layout.add_widget(scroll)
        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_menu())
        self.layout.add_widget(btn_retour)

    def ouvrir_recu(self, nom_fichier):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("DÉTAIL DU REÇU", 22))
        scroll = ScrollView()
        chemin = os.path.join(DOSSIER_RECUS, nom_fichier)
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                contenu = f.read()
        except Exception as e:
            contenu = f"Erreur de lecture : {e}"
        lbl_texte = Label(text=contenu, font_size=sp(12), size_hint_y=None, halign="left", valign="top", color=(1, 1, 1, 1))
        lbl_texte.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)),
                       texture_size=lambda inst, ts: setattr(inst, 'height', ts[1]))
        scroll.add_widget(lbl_texte)
        self.layout.add_widget(scroll)
        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_recus(None))
        self.layout.add_widget(btn_retour)

    # ====================================================
    # PARAMÈTRES & SAUVEGARDE & UTILISATEURS
    # ====================================================
    def afficher_parametres(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("PARAMÈTRES", 24))
        
        scroll = ScrollView()
        grille = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
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
        except Exception:
            pass
            
        self.param_inputs = {}
        champs = [("nom", "Nom de l'établissement (ex: DILEROM)"), ("adresse", "Adresse"), ("telephone", "Téléphone"), ("email", "Email"), ("nif", "NIF"), ("message", "Message du reçu")]
        
        for cle, label_txt in champs:
            lbl = Label(text=label_txt, font_size=sp(14), size_hint_y=None, height=dp(28), halign="left", color=(1, 1, 1, 1))
            lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
            inp = TextInput(text=params.get(cle, ""), multiline=False, font_size=sp(16), size_hint_y=None, height=dp(48))
            self.param_inputs[cle] = inp
            grille.add_widget(lbl)
            grille.add_widget(inp)
            
        scroll.add_widget(grille)
        self.layout.add_widget(scroll)
        
        self.msg_params = Label(text="", font_size=sp(14), size_hint=(1, None), height=dp(30))
        self.layout.add_widget(self.msg_params)
        
        btn_sauver = bouton("ENREGISTRER LES PARAMÈTRES", (0, 0.6, 0, 1), hauteur=50)
        btn_sauver.bind(on_press=self.sauvegarder_parametres)
        self.layout.add_widget(btn_sauver)

        btn_users = bouton("GÉRER LES UTILISATEURS", ORANGE, hauteur=50)
        btn_users.bind(on_press=self.afficher_utilisateurs)
        self.layout.add_widget(btn_users)

        btn_backup = bouton("SAUVEGARDER LA BASE", BLEU, hauteur=50)
        btn_backup.bind(on_press=self.sauvegarder_base)
        self.layout.add_widget(btn_backup)

        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
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
            self.msg_params.color = VERT
            self.msg_params.text = "Paramètres sauvegardés !"
        except Exception as e:
            self.msg_params.color = ROUGE
            self.msg_params.text = f"Erreur : {str(e)}"

    def sauvegarder_base(self, instance):
        try:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            nom_sauvegarde = f"sauvegarde_pharmacie_{date_str}.db"
            chemin_sauvegarde = os.path.join(App.get_running_app().user_data_dir, nom_sauvegarde)
            shutil.copy(CHEMIN_DB, chemin_sauvegarde)
            self._show_popup("Sauvegarde réussie", f"Votre base de données a été copiée ici :\n\n{chemin_sauvegarde}")
        except Exception as e:
            self._show_popup("Erreur de sauvegarde", str(e))

    # ====================================================
    # GESTION DES UTILISATEURS ET DES RÔLES
    # ====================================================
    def afficher_utilisateurs(self, instance):
        self.layout.clear_widgets()
        self.layout.add_widget(titre("GESTION DES UTILISATEURS", 22))

        self.user_spinner = Spinner(text="Sélectionnez un utilisateur", values=[], font_size=sp(16), size_hint=(1, None), height=dp(45), background_color=(0.2, 0.2, 0.2, 1))
        self.maj_liste_utilisateurs()
        self.layout.add_widget(self.user_spinner)

        btn_suppr = bouton("SUPPRIMER CET UTILISATEUR", ROUGE, hauteur=50)
        btn_suppr.bind(on_press=self.supprimer_utilisateur)
        self.layout.add_widget(btn_suppr)

        self.layout.add_widget(Label(text="Changer le mot de passe", font_size=sp(14), bold=True, color=ORANGE))
        self.reset_pass_input = champ("Nouveau mot de passe", password=True)
        self.layout.add_widget(self.reset_pass_input)
        
        btn_reset = bouton("CHANGER LE MOT DE PASSE", ORANGE, hauteur=45)
        btn_reset.bind(on_press=self.changer_mot_de_passe)
        self.layout.add_widget(btn_reset)

        self.layout.add_widget(Label(text="Ajouter un nouvel utilisateur", font_size=sp(16), bold=True, color=VERT))
        
        self.new_user_input = champ("Nouveau nom d'utilisateur")
        self.layout.add_widget(self.new_user_input)
        
        self.new_pass_input = champ("Nouveau mot de passe", password=True)
        self.layout.add_widget(self.new_pass_input)

        self.new_role_spinner = Spinner(text="Rôle", values=["caissier", "admin"], font_size=sp(16), size_hint=(1, None), height=dp(45), background_color=(0.2, 0.2, 0.2, 1))
        self.layout.add_widget(self.new_role_spinner)
        
        self.msg_users = Label(text="", font_size=sp(14), halign="center")
        self.layout.add_widget(self.msg_users)

        btn_ajouter = bouton("AJOUTER L'UTILISATEUR", (0, 0.5, 0, 1), hauteur=50)
        btn_ajouter.bind(on_press=self.ajouter_utilisateur)
        self.layout.add_widget(btn_ajouter)

        btn_retour = bouton("RETOUR", GRIS, hauteur=50)
        btn_retour.bind(on_press=lambda x: self.afficher_parametres(None))
        self.layout.add_widget(btn_retour)

    def maj_liste_utilisateurs(self):
        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            c.execute("SELECT username FROM utilisateurs")
            users = [row[0] for row in c.fetchall()]
            conn.close()
            self.user_spinner.values = users
        except Exception:
            pass

    def ajouter_utilisateur(self, instance):
        username = self.new_user_input.text.strip()
        password = self.new_pass_input.text.strip()
        role = self.new_role_spinner.text

        if not username or not password or role not in ["caissier", "admin"]:
            self.msg_users.color = ROUGE
            self.msg_users.text = "Veuillez remplir tous les champs."
            return

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            c.execute("SELECT id FROM utilisateurs WHERE username=?", (username,))
            if c.fetchone():
                self.msg_users.color = ROUGE
                self.msg_users.text = "Ce nom d'utilisateur existe déjà."
                conn.close()
                return

            sel = os.urandom(16).hex()
            mdp_hash = hashlib.sha256((sel + password).encode()).hexdigest()

            c.execute("INSERT INTO utilisateurs (username, sel, password_hash, role) VALUES (?, ?, ?, ?)", (username, sel, mdp_hash, role))
            conn.commit()
            conn.close()

            self.msg_users.color = VERT
            self.msg_users.text = f"Utilisateur '{username}' ({role}) ajouté !"
            self.new_user_input.text = ""
            self.new_pass_input.text = ""
            self.maj_liste_utilisateurs()

        except Exception as e:
            self.msg_users.color = ROUGE
            self.msg_users.text = f"Erreur : {str(e)}"

    def supprimer_utilisateur(self, instance):
        username = self.user_spinner.text
        if not username or username == "Sélectionnez un utilisateur":
            self.msg_users.color = ROUGE
            self.msg_users.text = "Sélectionnez un utilisateur."
            return

        if username == self.username_courant:
            self.msg_users.color = ROUGE
            self.msg_users.text = "Vous ne pouvez pas supprimer votre propre compte !"
            return

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            c.execute("DELETE FROM utilisateurs WHERE username=?", (username,))
            conn.commit()
            conn.close()
            
            self.msg_users.color = VERT
            self.msg_users.text = f"Utilisateur '{username}' supprimé."
            self.user_spinner.text = "Sélectionnez un utilisateur"
            self.maj_liste_utilisateurs()
        except Exception as e:
            self.msg_users.color = ROUGE
            self.msg_users.text = f"Erreur : {str(e)}"

    def changer_mot_de_passe(self, instance):
        username = self.user_spinner.text
        new_pass = self.reset_pass_input.text.strip()

        if not username or username == "Sélectionnez un utilisateur":
            self.msg_users.color = ROUGE
            self.msg_users.text = "Sélectionnez un utilisateur d'abord."
            return
        if not new_pass:
            self.msg_users.color = ROUGE
            self.msg_users.text = "Tapez un nouveau mot de passe."
            return

        try:
            conn = sqlite3.connect(CHEMIN_DB)
            c = conn.cursor()
            sel = os.urandom(16).hex()
            mdp_hash = hashlib.sha256((sel + new_pass).encode()).hexdigest()
            c.execute("UPDATE utilisateurs SET sel=?, password_hash=? WHERE username=?", (sel, mdp_hash, username))
            conn.commit()
            conn.close()
            
            self.msg_users.color = VERT
            self.msg_users.text = f"Mot de passe de '{username}' modifié !"
            self.reset_pass_input.text = ""
        except Exception as e:
            self.msg_users.color = ROUGE
            self.msg_users.text = f"Erreur : {str(e)}"

if __name__ == '__main__':
    PharmacieApp().run()
