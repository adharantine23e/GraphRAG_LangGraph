I want to suck some pp :V

# Workflow

    Initiate the chatbot ---> Give the username ---> Give the previous chat history ----------
                                                                                             |
    Initate the Neo4j Graph                                                                  |                                                   
                ^                                                                            V                                                                 
                |                                                                       Input text                                              
                |                                                                            |
                |                                                                            |---------------------------------------------------        
                |                                                                            V                                                  |
                |                                                Extract key words from the input text (e.g: "Cảm", "Đau bụng", "Dick", etc)    |
                |                                                                            |                                                  |
                |                                                                            |--------------------------------------------------|--------   
                |                                                                            V                                                  |        |
                |                                                        Retrieve the graph link of the entities extracted                      |        |
                |                                                                            |                                                  |        |
                |                                                                            |                                                  |        |
                |                                                                            V                                                  |        |
                |                                                        Retrieve the documents related to the input <---------------------------        |
                |                                                                            |                                                           |
                |                                                                            |                                                           |
                |                                                                            V                                                           |
                ---------------------------------------------------------------------- Final output <---------------------------------------------------
                |                       Logging process
                V
    Temporary storage for quick acesss