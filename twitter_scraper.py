import time
import csv
import re
import random
import os
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains

class TwitterScraper:
    def __init__(self, headless=False):
        """Inicializar el scraper de Twitter/X."""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")  # Modo headless más reciente
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-automation")  # Evitar detección de automatización
        
        # Configuraciones para evitar detección
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Agregar user-agent personalizado para reducir probabilidad de bloqueo
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 15)
        self.actions = ActionChains(self.driver)
        
    def __del__(self):
        """Cerrar el navegador cuando se destruye el objeto."""
        try:
            self.driver.quit()
        except:
            pass
    
    def scroll_down(self, num_scrolls=5, pause=2):
        """Desplazar hacia abajo para cargar más tweets."""
        for i in range(num_scrolls):
            print(f"Scroll {i+1}/{num_scrolls}")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(pause * 0.8, pause * 1.2))  # Pausa aleatoria
            
            # Verificar si hay una ventana emergente de inicio de sesión y cerrarla
            try:
                close_buttons = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="modal-close"], [role="button"][aria-label*="Close"], button[aria-label*="Close"]')
                if close_buttons:
                    close_buttons[0].click()
                    print("Ventana emergente cerrada")
                    time.sleep(1)
            except:
                pass
    
    def extract_stat_direct(self, tweet, data_testid):
        """Extraer estadística directamente usando data-testid."""
        try:
            # Intentar encontrar el elemento específico por data-testid
            group_elements = tweet.find_elements(By.CSS_SELECTOR, f'[data-testid="{data_testid}"]')
            if not group_elements:
                return 0
                
            group_element = group_elements[0]
            
            # En Twitter/X, el texto con el número está en un span dentro del elemento con data-testid
            # o podría estar en el aria-label del elemento padre
            try:
                # Intentar obtener del aria-label
                parent = group_element.find_element(By.XPATH, './..')
                aria_label = parent.get_attribute('aria-label')
                if aria_label:
                    print(f"Aria-label encontrado para {data_testid}: {aria_label}")
                    return extract_number(aria_label)
                
                # Si no hay aria-label, intentar obtener del texto
                spans = group_element.find_elements(By.CSS_SELECTOR, 'span')
                for span in spans:
                    span_text = span.text.strip()
                    if span_text:
                        print(f"Texto encontrado para {data_testid}: {span_text}")
                        return extract_number(span_text)
                
                return 0
            except Exception as e:
                print(f"Error al extraer texto para {data_testid}: {e}")
                return 0

        except NoSuchElementException:
            print(f"No se encontró elemento para {data_testid}")
            return 0
        except Exception as e:
            print(f"Error general al buscar {data_testid}: {e}")
            return 0
    
    def extract_tweet_stats(self, tweet):
        """Extraer estadísticas de un tweet (me gusta, comentarios, retweets)."""
        stats = {
            'comentarios': 0,
            'retweets': 0,
            'me_gusta': 0,
            'compartidos': 0
        }
        
        # Asegurarnos de que el tweet es visible y esperar a que se carguen las estadísticas
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet)
        time.sleep(1)  # Esperar más tiempo para que se carguen las estadísticas
        
        try:
            # Método 1: Buscar directamente por data-testid
            data_testids = {
                'reply': 'comentarios',
                'retweet': 'retweets',
                'like': 'me_gusta',
                'bookmark': 'compartidos'
            }
            
            for testid, stat_key in data_testids.items():
                value = self.extract_stat_direct(tweet, testid)
                if value > 0:  # Solo actualizar si encontramos un valor positivo
                    stats[stat_key] = value
                    
            # Si no encontramos nada, intentamos el método alternativo
            if all(v == 0 for v in stats.values()):
                print("Intentando método alternativo para extraer estadísticas...")
                
                # Método 2: Buscar todos los elementos con role="button" dentro de groups
                metrics_groups = tweet.find_elements(By.CSS_SELECTOR, '[role="group"] [role="button"]')
                for metric in metrics_groups:
                    try:
                        # Obtener el texto y el aria-label
                        aria_text = metric.get_attribute('aria-label') or ""
                        inner_text = metric.text or ""
                        
                        # Usar el texto que tenga información
                        metric_text = aria_text if len(aria_text) > len(inner_text) else inner_text
                        metric_text = metric_text.lower()
                        
                        print(f"Texto de métrica encontrado: {metric_text}")
                        
                        # Check que tipo de métrica es
                        if any(keyword in metric_text for keyword in ["repl", "respuesta", "comment"]):
                            stats['comentarios'] = extract_number(metric_text)
                        elif any(keyword in metric_text for keyword in ["retweet", "retuit"]):
                            stats['retweets'] = extract_number(metric_text)
                        elif any(keyword in metric_text for keyword in ["like", "me gusta"]):
                            stats['me_gusta'] = extract_number(metric_text)
                        elif any(keyword in metric_text for keyword in ["bookmark", "guardar", "compartir"]):
                            stats['compartidos'] = extract_number(metric_text)
                    except StaleElementReferenceException:
                        print("Elemento ya no está disponible (stale)")
                        continue
                    except Exception as e:
                        print(f"Error al procesar métrica: {e}")
                        continue
            
            # Método 3: Si aún tenemos ceros, intentemos extraer números directamente
            if all(v == 0 for v in stats.values()):
                print("Intentando extraer números directamente del tweet...")
                all_spans = tweet.find_elements(By.CSS_SELECTOR, 'span')
                for span in all_spans:
                    try:
                        span_text = span.text.strip()
                        if span_text and re.match(r'^\d+$', span_text):  # Solo números
                            # Intentar determinar el tipo de métrica por su posición o contexto
                            parent = span.find_element(By.XPATH, './..')
                            grandparent = parent.find_element(By.XPATH, './..')
                            
                            # Verificar si hay iconos cercanos que indiquen el tipo
                            outer_html = grandparent.get_attribute('outerHTML').lower()
                            if "comment" in outer_html or "reply" in outer_html:
                                stats['comentarios'] = int(span_text)
                            elif "retweet" in outer_html:
                                stats['retweets'] = int(span_text)
                            elif "like" in outer_html or "heart" in outer_html:
                                stats['me_gusta'] = int(span_text)
                            elif "bookmark" in outer_html or "share" in outer_html:
                                stats['compartidos'] = int(span_text)
                    except:
                        continue
                
        except Exception as e:
            print(f"Error general al extraer estadísticas: {e}")

        print(f"Estadísticas finales extraídas: {stats}")
        return stats
    
    def extract_tweet_content(self, tweet):
        """Extraer el contenido del tweet."""
        try:
            tweet_text_elements = tweet.find_elements(By.CSS_SELECTOR, '[data-testid="tweetText"]')
            if tweet_text_elements:
                return tweet_text_elements[0].text
        except:
            pass
            
        # Intentar selectores alternativos
        selectors = ['div[lang]', 'div[dir="auto"]', 'div[role="group"] div[dir="auto"]']
        for selector in selectors:
            try:
                elements = tweet.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    text = element.text.strip()
                    if text and len(text) > 5:  # Probablemente sea el texto del tweet
                        return text
            except:
                continue
                
        return ""

    def extract_tweet_date(self, tweet):
        """Extraer la fecha del tweet."""
        try:
            time_elements = tweet.find_elements(By.TAG_NAME, "time")
            if time_elements:
                return time_elements[0].get_attribute("datetime")
        except:
            pass
            
        # Intentar con selectores alternativos
        try:
            # Buscar elementos con atributos de tiempo
            time_elements = tweet.find_elements(By.CSS_SELECTOR, '[datetime]')
            if time_elements:
                return time_elements[0].get_attribute("datetime")
        except:
            pass
            
        return ""
    
    def extract_tweet_url(self, tweet):
        """Extraer la URL del tweet."""
        try:
            # Buscar enlaces que contengan "/status/" en su URL
            link_elements = tweet.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
            if link_elements:
                return link_elements[0].get_attribute("href")
        except:
            pass
            
        # Método alternativo: buscar el timestamp que suele ser un enlace al tweet
        try:
            time_elements = tweet.find_elements(By.CSS_SELECTOR, 'time')
            if time_elements:
                time_link = time_elements[0].find_element(By.XPATH, './..')
                if time_link.tag_name == 'a':
                    return time_link.get_attribute("href")
        except:
            pass
        
        # Tercer método: buscar cualquier enlace que contenga un ID de tweet (números largos)
        try:
            links = tweet.find_elements(By.TAG_NAME, 'a')
            for link in links:
                href = link.get_attribute('href') or ""
                if '/status/' in href and re.search(r'/status/\d+', href):
                    return href
        except:
            pass
            
        return ""
    
    def has_media(self, tweet):
        """Verificar si el tweet tiene imágenes o videos."""
        try:
            # Buscar diversos tipos de media
            media_selectors = [
                '[data-testid="tweetPhoto"]', 
                'video',
                'img[src*="pbs.twimg.com"]',
                '[data-testid="videoPlayer"]',
                '[data-testid="mediaPreview"]'
            ]
            
            for selector in media_selectors:
                elements = tweet.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    return True
            return False
        except:
            return False
    
    def is_tweet_less_than_two_years_old(self, date_str):
        """Verificar si un tweet tiene menos de dos años desde su publicación."""
        if not date_str:
            return False
            
        try:
            # Parseamos la fecha del tweet (formato ISO)
            # Manejar diferentes formatos posibles
            if 'Z' in date_str:
                date_str = date_str.replace('Z', '+00:00')
                
            tweet_date = datetime.datetime.fromisoformat(date_str)
            
            # Fecha actual
            current_date = datetime.datetime.now(datetime.timezone.utc)
            
            # Asegurarnos que tweet_date tenga información de zona horaria
            if tweet_date.tzinfo is None:
                tweet_date = tweet_date.replace(tzinfo=datetime.timezone.utc)
                
            # Diferencia en días
            days_difference = (current_date - tweet_date).days
            
            # Verificar si es menor a 2 años (730 días aproximadamente)
            is_recent = days_difference < 730
            
            print(f"Fecha del tweet: {tweet_date}, Diferencia de días: {days_difference}, Es reciente: {is_recent}")
            return is_recent
        except Exception as e:
            print(f"Error al verificar la antigüedad del tweet: {e}")
            return False
    
    def get_account_name(self, account_url):
        """Obtener el nombre de usuario de la URL de cuenta."""
        if not account_url:
            return "unknown"
            
        try:
            # Limpiar la URL para extraer solo el nombre de usuario
            handle = account_url.rstrip('/').split('/')[-1]
            # Eliminar parámetros de query si existen
            if '?' in handle:
                handle = handle.split('?')[0]
            return handle
        except:
            return "unknown"
            
    def scrape_account(self, account_url, num_tweets=20):
        """Raspar tweets de una cuenta específica de Twitter/X."""
        try:
            self.driver.get(account_url)
            print(f"Accediendo a: {account_url}")
            
            # Esperar a que cargue la página
            selectors = ['[data-testid="tweet"]', 'article', '[data-testid="cellInnerDiv"]']
            found = False
            
            for selector in selectors:
                try:
                    self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    print(f"Página cargada, encontrado selector: {selector}")
                    found = True
                    break
                except TimeoutException:
                    continue
                    
            if not found:
                print("No se pudo cargar la página correctamente")
                return []
                
            # Verificar si hay un popup de inicio sesión y cerrarlo
            try:
                close_buttons = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="modal-close"], [role="button"][aria-label*="Close"], button[aria-label*="Close"]')
                if close_buttons:
                    close_buttons[0].click()
                    print("Popup de inicio de sesión cerrado")
                    time.sleep(1)
            except:
                pass
            
            # Scroll para cargar más tweets - aumentamos el número para conseguir suficientes tweets recientes
            num_scrolls_needed = max(7, num_tweets // 2)  # Más scrolls para asegurar cargar suficientes tweets
            self.scroll_down(num_scrolls_needed, pause=2)
            
            # Recolectar tweets con diferentes selectores
            tweet_elements = []
            selectors = [
                '[data-testid="tweet"]',
                'article',
                '[data-testid="cellInnerDiv"] div[data-testid]',
                '[data-testid="cellInnerDiv"]'
            ]
            
            for selector in selectors:
                tweet_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if len(tweet_elements) > 0:
                    print(f"Encontrados {len(tweet_elements)} tweets con selector: {selector}")
                    break
            
            if not tweet_elements:
                print("No se encontraron tweets con ninguno de los selectores")
                return []
            
            # Filtrar tweets que parezcan promocionados o repetidos
            filtered_tweets = []
            tweet_urls = set()
            
            for tweet in tweet_elements:
                try:
                    # Verificar si parece un tweet promocionado
                    is_promoted = False
                    try:
                        promoted_labels = tweet.find_elements(By.CSS_SELECTOR, '[data-testid="socialProof"]')
                        if promoted_labels:
                            is_promoted = True
                    except:
                        pass
                    
                    if is_promoted:
                        continue
                    
                    # Extraer URL para verificar duplicados
                    url = self.extract_tweet_url(tweet)
                    if url and url not in tweet_urls:
                        tweet_urls.add(url)
                        filtered_tweets.append(tweet)
                except Exception as e:
                    print(f"Error al filtrar tweet: {e}")
                    continue
                    
            print(f"Después de filtrar: {len(filtered_tweets)} tweets únicos")
            
            # Extraer datos de los tweets
            tweets_data = []
            account_handle = self.get_account_name(account_url)
            tweets_processed = 0
            
            for i, tweet in enumerate(filtered_tweets):
                try:
                    # Hacer scroll al tweet para asegurar que está en la vista
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tweet)
                    time.sleep(0.5)  # Esperar a que se carguen los contadores
                    
                    # Extraer la fecha primero para filtrar por antigüedad
                    tweet_date = self.extract_tweet_date(tweet)
                    
                    # Si no pudimos extraer la fecha, intentamos seguir con el tweet
                    if not tweet_date:
                        print(f"Advertencia en tweet {i+1}: no se pudo extraer la fecha, pero continuamos")
                    else:
                        # Verificar si el tweet tiene menos de dos años
                        if not self.is_tweet_less_than_two_years_old(tweet_date):
                            print(f"Saltando tweet {i+1}: es más antiguo que 2 años")
                            continue
                    
                    # Continuar con la extracción de datos
                    tweet_text = self.extract_tweet_content(tweet)
                    tweet_url = self.extract_tweet_url(tweet)
                    has_media = self.has_media(tweet)
                    
                    tweet_data = {
                        'cuenta': account_handle,
                        'texto': tweet_text or "",  # Asegurar que no sea None
                        'fecha': tweet_date or "",  # Asegurar que no sea None
                        'url': tweet_url or "",     # Asegurar que no sea None
                        'tiene_media': has_media,
                        'comentarios': 0,
                        'retweets': 0,
                        'me_gusta': 0,
                        'compartidos': 0
                    }
                    
                    # Extraer estadísticas
                    try:
                        stats = self.extract_tweet_stats(tweet)
                        tweet_data.update(stats)
                    except Exception as stat_error:
                        print(f"Error al extraer estadísticas: {stat_error}")
                        # Mantenemos los valores por defecto (ceros)
                    
                    # Agregar el tweet a nuestra colección
                    tweets_data.append(tweet_data)
                    print(f"Tweet {i+1} extraído: {tweet_text[:30]}..." if tweet_text else "Sin texto")
                    tweets_processed += 1
                    
                    # Si ya tenemos suficientes tweets, salimos
                    if tweets_processed >= num_tweets:
                        break
                    
                except StaleElementReferenceException:
                    print(f"Error: Elemento ya no disponible (stale) para tweet {i+1}")
                    continue
                except Exception as e:
                    print(f"Error general al extraer tweet {i+1}: {e}")
                    continue
            
            print(f"Total de tweets válidos extraídos: {len(tweets_data)}")
            return tweets_data
            
        except Exception as e:
            print(f"Error global al raspar cuenta {account_url}: {e}")
            return []
    
    def scrape_multiple_accounts(self, account_urls, output_dir='twitter_data', num_tweets_per_account=20):
        """
        Raspar múltiples cuentas de Twitter/X y guardar los resultados en archivos CSV separados.
        Cada extracción genera un nuevo archivo con marca de tiempo en el directorio especificado.
        """
        # Crear directorio de salida si no existe
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Directorio creado: {output_dir}")
            
        # Generar un timestamp para esta extracción
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Estadísticas generales
        all_tweets_count = 0
        accounts_stats = {}
        
        # Procesamos cada cuenta por separado
        for url in account_urls:
            print(f"\n{'='*50}\nRaspando cuenta: {url}\n{'='*50}")
            
            # Obtener el nombre de usuario de la URL
            account_handle = self.get_account_name(url)
            
            # Crear nombre de archivo para esta cuenta
            filename = f"{account_handle}_{timestamp}.csv"
            output_file = os.path.join(output_dir, filename)
            
            # Raspar tweets de esta cuenta
            tweets = self.scrape_account(url, num_tweets_per_account)
            
            # Guardar resultados en CSV específico para esta cuenta
            if tweets:
                fieldnames = ['cuenta', 'texto', 'fecha', 'url', 'comentarios', 'retweets', 'me_gusta', 'compartidos', 'tiene_media']
                
                # Asegurar que todos los tweets tienen todos los campos
                for tweet in tweets:
                    for field in fieldnames:
                        if field not in tweet:
                            tweet[field] = ""
                
                try:
                    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(tweets)
                    
                    print(f"\nDatos de {account_handle} guardados en {output_file}")
                except Exception as e:
                    print(f"Error al guardar el archivo CSV para {account_handle}: {e}")
                
                # Actualizar estadísticas
                all_tweets_count += len(tweets)
                accounts_stats[account_handle] = len(tweets)
                
                # Mostrar ejemplos de métricas para esta cuenta
                if tweets:
                    print("\nEjemplos de métricas encontradas:")
                    for i, tweet in enumerate(tweets[:3]):
                        print(f"\nEjemplo {i+1}:")
                        print(f"Fecha: {tweet.get('fecha', 'No disponible')}")
                        texto = tweet.get('texto', '')
                        print(f"Texto: {texto[:50]}..." if len(texto) > 50 else texto)
                        print(f"Comentarios: {tweet.get('comentarios', 0)}")
                        print(f"Retweets: {tweet.get('retweets', 0)}")
                        print(f"Me gusta: {tweet.get('me_gusta', 0)}")
                        print(f"Compartidos: {tweet.get('compartidos', 0)}")
            else:
                print(f"No se pudieron extraer tweets de la cuenta {account_handle}")
            
            # Pausa entre cuentas para evitar detección
            time.sleep(random.uniform(5, 8))
        
        # Guardar también un resumen general de esta extracción
        try:
            summary_file = os.path.join(output_dir, f"resumen_extraccion_{timestamp}.csv")
            with open(summary_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Cuenta', 'Tweets Extraídos', 'Fecha Extracción'])
                for account, count in accounts_stats.items():
                    writer.writerow([account, count, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
            
            print(f"\nResumen de la extracción guardado en {summary_file}")
        except Exception as e:
            print(f"Error al guardar el archivo de resumen: {e}")
        
        print(f"\n{'='*50}")
        print(f"Total de tweets recolectados: {all_tweets_count}")
        print(f"Tweets por cuenta:")
        for account, count in accounts_stats.items():
            print(f"- {account}: {count} tweets")
        print(f"{'='*50}")

def extract_number(text):
    """Extraer número de texto como '5 respuestas' o '10.2K Me gusta'."""
    if not text:
        return 0
        
    # Primero, intentemos encontrar patrones comunes de Twitter con K/M
    k_pattern = re.search(r'(\d+(?:[.,]\d+)?)[kK]', text)
    m_pattern = re.search(r'(\d+(?:[.,]\d+)?)[mM]', text)
    
    if k_pattern:
        return int(float(k_pattern.group(1).replace(',', '.')) * 1000)
    if m_pattern:
        return int(float(m_pattern.group(1).replace(',', '.')) * 1000000)
    
    # Buscar patrones como "mil" o "millones"
    if 'mil' in text.lower():
        mil_pattern = re.search(r'(\d+(?:[.,]\d+)?)\s*mil', text.lower())
        if mil_pattern:
            return int(float(mil_pattern.group(1).replace(',', '.')) * 1000)
    
    if 'millon' in text.lower() or 'millones' in text.lower():
        mill_pattern = re.search(r'(\d+(?:[.,]\d+)?)\s*millon(?:es)?', text.lower())
        if mill_pattern:
            return int(float(mill_pattern.group(1).replace(',', '.')) * 1000000)
    
    # Finalmente, buscar cualquier número
    number_pattern = re.search(r'(\d+(?:[.,]\d+)?)', text)
    if number_pattern:
        # Manejar delimitadores decimales
        return int(float(number_pattern.group(1).replace(',', '.')))
    
    return 0

# Ejemplo de uso
if __name__ == "__main__":  
    # Lista de cuentas a raspar
    accounts = [
        "https://x.com/BurgerKingMX",
        "https://x.com/KFC_MEXICO",
        "https://x.com/littlecaesarsmx"
    ]
    
    # Iniciar el scraper (False para ver el navegador, True para modo headless)
    scraper = TwitterScraper(headless=False)
    
    try:
        # Directorio donde se guardarán los archivos CSV
        output_directory = "twitter_extracciones"
        
        # Raspar tweets por cuenta (20 tweets por cuenta, menos de 2 años de antigüedad)
        scraper.scrape_multiple_accounts(accounts, output_directory, 20)
    finally:
        # Asegurar que el navegador se cierre correctamente
        del scraper