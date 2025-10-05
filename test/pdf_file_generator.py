import fitz  # PyMuPDF

long_texts = \
    ["""
    In the distant realm of Zephyria, where the crystalline rivers sang melodies to the emerald forests, a peculiar event unfolded beneath the azure sky. Luminescent creatures known as Ethereal Wisps danced in a mesmerizing display, weaving trails of iridescence through the air. The Whispering Willows, ancient sentinels of the land, swayed in harmony, sharing secrets carried by the winds for centuries.
    Meanwhile, on the outskirts of the Enchanted Glade, a curious inventor named Elara tinkered with arcane contraptions that hummed with latent magic. Elara, with her copper goggles gleaming, sought to unveil the mysteries of a forgotten celestial alignment. Legends spoke of a cosmic conjunction that could unlock the hidden powers of the Starlight Nexus, an ethereal nexus rumored to grant unimaginable wisdom.
    As dusk settled, casting a kaleidoscope of hues across the horizon, a lone bard named Seraphina emerged from the Shadowed Vale. Seraphina carried a lute carved from the wood of the Eldertree, a relic believed to resonate with the pulse of the earth itself. Her melodic tunes had the power to mend broken spirits and stir ancient memories.
    The town of Astral Haven bustled with activity as its residents prepared for the impending Celestial Gala, an event held once every millennium. The grandiose gala was rumored to be the key to unlocking the dormant energies within the Starlight Nexus. Elders passed down tales of a chosen one, destined to navigate the celestial labyrinth and awaken the nexus's latent potential.
    Unbeknownst to the inhabitants of Zephyria, an enigmatic figure named Orion observed from the Astral Observatory, cloaked in the cosmic glow of constellations. Orion, a keeper of cosmic balance, sensed a disturbance in the celestial energies. Whispers of an ancient prophecy echoed through the astral winds, foretelling a convergence that could shape the destiny of Zephyria.
    As the first stars began to twinkle in the indigo sky, Elara, Seraphina, and Orion found their fates entwined in the celestial dance, bound by threads of destiny that shimmered like stardust. The journey to unravel the secrets of the Starlight Nexus had begun, and the pages of Zephyria's untold story unfurled with each passing moment.
    """
    , """Page 1:
    Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer nec odio. Praesent libero. Sed cursus ante dapibus diam. Sed nisi.
    Nulla quis sem at nibh elementum imperdiet. Duis sagittis ipsum. Praesent mauris. Fusce nec tellus sed augue semper porta.
    Mauris massa. Vestibulum lacinia arcu eget nulla. Class aptent taciti sociosqu ad litora torquent per conubia nostra, per inceptos himenaeos.
    Curabitur sodales ligula in libero. Sed dignissim lacinia nunc. Curabitur tortor.
    Page 2:
    In hac habitasse platea dictumst. Integer sagittis neque a tortor. Integer aliquam velit ac mauris. Integer in mauris eu nibh euismod gravida.
    Duis ac tellus et risus vulputate vehicula. Donec lobortis risus a elit. Etiam tempor. Ut ullamcorper, ligula eu tempor congue, eros est euismod turpis,
    id tincidunt sapien risus a quam. Maecenas fermentum consequat mi. Donec fermentum. Pellentesque malesuada nulla a mi. Duis sapien sem,
    aliquet nec, commodo eget, consequat quis, neque.
    Page 3:
    Aliquam faucibus, elit ut dictum aliquet, felis nisl adipiscing sapien, sed malesuada diam lacus eget erat. Cras mollis scelerisque nunc.
    Nullam arcu. Aliquam consequat. Curabitur augue lorem, dapibus quis, laoreet et, pretium ac, nisi. Aenean magna nisl, mollis quis, molestie eu,
    feugiat in, orci. In hac habitasse platea dictumst. Ut ac justo sit amet dolor ornare cursus. Curabitur blandit mollis lacus.
    """
    , """y"""
    ]

def generate_pdf(file_path, num_pages):
    # Create a PDF document
    doc = fitz.open()

    # Add a page
    page = doc.new_page()

    tw = fitz.TextWriter(page.rect)
    tw.append(pos=(50,50), text=long_texts[0], fontsize=11)
    tw.write_text(page)

    # Save the document to the specified output path
    doc.save(file_path)

    # Close the document
    doc.close()

# Generate PDF with one page
generate_pdf('file1.pdf', 1)

# Generate PDF with three pages
#generate_pdf('file2.pdf', 3)

# Generate PDF with five pages
#generate_pdf('file3.pdf', 5)