# Picnic-Day-Scrapers
A list of webs scrapers that I could not find as services online and found similar ones on GitHub too hard to implement.

You just need python setup on your system, check requirements.txt for the libraries installed. I use pip. These tools are not 100% complete but still surpass tools available in either ease of use or complexity or effectiveness or any two or even all three at this current time of publishing [28/02/2025]

The tool catches links within paginated components but not ajax. To improve this, first observe the ajax endpoints from the networks section of dev tools, observe the information and setup flags according to that.


I choose to name these scrapers Picnic Day Scrapers because I made them right before going on a picnic. I would be in gratitude if this name was carried on in your future projects should this project be of any use to you.

Thankyou,
hamzaskhan

Contents
-WBSLSCv4.py: It scrapes all the internal links of the website you enter and creates a tree sturcture of all links in order to understand the relashionship and flow. It then creates a list of all unique links 
 which is essentially a list of all links in the website in list form.
-brokenScraperv2.96.5.py: It takes a .csv or .txt as input. Each line in either format should contain one link. Each link is checked for error. Check line number 15 for extending it's functionality.
